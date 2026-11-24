#!/usr/bin/env python3
"""Fairy2iOS KTGL coherent 2GiB configuration repair without shader rebuild.

Rebuild from SHA-pinned 44995690307 PRE-RESOURCE-FALLBACK IPA.
The earlier fix replaced two loads of config+0xE0 by a 2GiB MOVZ, so
other KTGL consumers could still see the OLD dynamic capacity. Fix the
shared 64-bit field once at initialization and reinstate its second load.

Do not install G1T/G1S, zlib or direct reader synthetic retry hooks.
The result is a CANDIDATE until tested on a real iPhone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
import repack_full_resource_va as base

ROOT_PATCH=base.patch_main
OLD_SITE=0x21b6924    # originally: LDR x8, [x27,#0xe0]
SECOND=0x21b6954      # originally: LDR x25,[x27,#0xe0]
ORIGINAL_FIRST=bytes.fromhex("687340f9")
ORIGINAL_SECOND=bytes.fromhex("797340f9")
OLD_BROKEN_FIRST=bytes.fromhex("0800a4d2")
OLD_BROKEN_SECOND=bytes.fromhex("1900a4d2")
STORE_CAP=bytes.fromhex("687300f9")  # STR x8,[x27,#0xe0]
STUB_MOVZ=OLD_BROKEN_FIRST              # MOVZ x8,#0x2000,LSL#16
CAPACITY_UNITS=0x20000000
CAPACITY_BYTES=CAPACITY_UNITS<<2
STUB_AT=0x2d6b050

def check_ktgl_structure(raw:bytes, stamp:dict):
    """Verify this is executable zero padding AFTER 5GiB trampolins."""
    base.require(STUB_AT+12<=len(raw) and STUB_AT>=base.PATCH_OFF,
                 "KTGL cave is not executable __dmmainx1")
    start=int(stamp["code_cave"].split("+0x",1)[1],16)
    base.require(STUB_AT == start+5*base.CAVE_STRIDE,
                 "KTGL cave does not directly follow five audited 5GiB root stubs")
    base.require(raw[STUB_AT:STUB_AT+12]==bytes(12),
                 "KTGL cave contains code/data: refuse overwrite")
    base.require(raw[OLD_SITE:OLD_SITE+4]==OLD_BROKEN_FIRST and
                 raw[SECOND:SECOND+4]==OLD_BROKEN_SECOND,
                 "source lacks exactly the two KNOWN incorrect fixed-size loads")
    base.require(CAPACITY_BYTES==0x80000000,"must preserve measured 2GiB graphics clearance")
    return start

def coherent_patch(raw:bytes, stamp:dict):
    check_ktgl_structure(raw,stamp)
    out=bytearray(raw)
    # First consumer will initialize the SAME shared field other readers use.
    # x8 is already the value the old MOVZ produced. No other regs/flags change.
    out[OLD_SITE:OLD_SITE+4]=base.branch_opcode(OLD_SITE,STUB_AT)
    # Second consumer again uses the value from the shared KTGL configuration.
    out[SECOND:SECOND+4]=ORIGINAL_SECOND
    # AArch64: MOVZ x8,#0x2000,lsl#16; STR x8,[x27,#0xe0];
    #           B site+4. Use original shift-by-2 at the callsite.
    stub=STUB_MOVZ+STORE_CAP+base.branch_opcode(STUB_AT+8,OLD_SITE+4)
    out[STUB_AT:STUB_AT+len(stub)]=stub
    base.require(out[OLD_SITE:OLD_SITE+4]==base.branch_opcode(OLD_SITE,STUB_AT),
                 "invalid forward branch to shared capacity write")
    base.require(out[SECOND:SECOND+4]==ORIGINAL_SECOND,
                 "second read must use the original dynamic field")
    changes=[i for i in (OLD_SITE,SECOND,STUB_AT,STUB_AT+4,STUB_AT+8)
             if out[i:i+4]!=raw[i:i+4]]
    base.require(changes==[OLD_SITE,SECOND,STUB_AT,STUB_AT+4,STUB_AT+8],
                 "not exactly the proven 2-site + 3-word consistency change")
    return bytes(out),{
        "source_field":"[x27 + 0xe0], u64",
        "old_two_consumer_behavior":"movz x8/x25, 0x20000000; global config untouched",
        "new_one_shared_source":"first consumer writes 0x20000000 to config then uses it; second consumer reloads config",
        "new_capacity_bytes":CAPACITY_BYTES,
        "original_reader_instruction_restored":ORIGINAL_SECOND.hex(),
        "patched_first_instruction_branch":base.branch_opcode(OLD_SITE,STUB_AT).hex(),
        "staged_stub":stub.hex(),
        "shared_field_write_location":f"main+0x{STUB_AT+4:x}",
        "guest_instruction_changes_after_5g":len(changes),
        "patch_origins":[f"main+0x{x:x}" for x in changes],
        "no_bypass_of_original_g1t_g1s_parsers":True,
        "no_inflator_or_direct_reader_brk":True,
        "not_verified_on_device":True,
    }

def patch_main(exe:Path,oldreport:dict):
    stamp=ROOT_PATCH(exe,oldreport)
    parts,raw=base.main_sections(exe)
    coherent,proof=coherent_patch(raw,stamp)
    start=parts["x0"]["size"]
    if "native_drs" in proof:
        from ktgl_native_fps import DRS_SLOT,DRS_SEED,verify_drs
        verify_drs(coherent,start,base.PATCH_OFF)
        base.require(raw[DRS_SLOT:DRS_SLOT+8]==bytes(8) and
                     coherent[start:DRS_SLOT]==raw[start:DRS_SLOT] and
                     coherent[DRS_SLOT:DRS_SLOT+8]==DRS_SEED and
                     coherent[DRS_SLOT+8:base.PATCH_OFF]==raw[DRS_SLOT+8:base.PATCH_OFF],
                     "only the reviewed eight-byte DRS slot may change in W")
        write_sections=(("x0",0),("w",start),("x1",base.PATCH_OFF))
    else:
        base.require(coherent[start:base.PATCH_OFF]==raw[start:base.PATCH_OFF],
                     "signed guest __DMmainW data unexpectedly altered")
        write_sections=(("x0",0),("x1",base.PATCH_OFF))
    with exe.open("r+b") as f:
        for key,off in write_sections:
            item=parts[key];new=coherent[off:off+item["size"]]
            f.seek(item["offset"])
            base.require(f.read(item["size"])==item["data"],
                         "guest altered while staging KTGL patch")
            f.seek(item["offset"]);f.write(new)
    p,actual=base.main_sections(exe)
    base.require(actual==coherent,"Mach-O sections mismatch after KTGL patch")
    stamp["after_sha256"]=hashlib.sha256(coherent).hexdigest()
    for key in ("x0","x1"):
        stamp[key+"_after_sha256"]=hashlib.sha256(p[key]["data"]).hexdigest()
    if "native_drs" in proof:
        stamp["w_before_drs_sha256"]=stamp["w_sha256"]
        stamp["w_sha256"]=hashlib.sha256(p["w"]["data"]).hexdigest()
    stamp["coherent_ktgl_shared_capacity"]=proof
    return stamp

def verify_main(exe:Path,stamp:dict):
    parts,raw=base.main_sections(exe)
    base.require(hashlib.sha256(raw).hexdigest()==stamp["after_sha256"],
                 "guest code changed in native host rebuild")
    for key in ("x0","x1"):
        base.require(hashlib.sha256(parts[key]["data"]).hexdigest()
                     ==stamp[key+"_after_sha256"],"repacked "+key+" changed")
    base.require(hashlib.sha256(parts["w"]["data"]).hexdigest()==stamp["w_sha256"],
                 "guest RO/data changed")
    # All five original 5GiB root producers and generated trampolins are retained.
    cave=int(stamp["code_cave"].split("+0x",1)[1],16)
    for i,(site,reg) in enumerate(base.ROOT_SITES):
        at=cave+i*base.CAVE_STRIDE
        expected=(0xd2c00020|reg).to_bytes(4,"little") + (
                  0xf2a80000|reg).to_bytes(4,"little") + base.branch_opcode(at+8,site+4)
        base.require(raw[site:site+4]==base.branch_opcode(site,at) and
                     raw[at:at+12]==expected,
                     f"5GiB root producer lost main+0x{site:x}")
    for at,code in base.PRESERVE:
        if at in (OLD_SITE,SECOND): continue
        base.require(raw[at:at+4]==bytes.fromhex(code),
                     f"unrelated heap/alignment patch drift at main+0x{at:x}")
    base.require(raw[OLD_SITE:OLD_SITE+4]==base.branch_opcode(OLD_SITE,STUB_AT)
                 and raw[SECOND:SECOND+4]==ORIGINAL_SECOND
                 and raw[STUB_AT:STUB_AT+12]==bytes.fromhex(
                     stamp["coherent_ktgl_shared_capacity"]["staged_stub"]),
                 "shared KTGL region is not initialized and read coherently")
    for site,opcode in ((0xc11b80,bytes.fromhex("08a440a9")),
                        (0xc11f9c,bytes.fromhex("e00313aa")),
                        (0xc0ef8c,bytes.fromhex("e9e30191")),
                        (0xc0f0d4,bytes.fromhex("e0031f2a"))):
        base.require(raw[site:site+4]==opcode,
                     f"speculative guest reader/codec hook survived main+0x{site:x}")

def make(source:Path,source_report:Path,repo:Path,output:Path):
    base.patch_main=patch_main
    base.verify_main=verify_main
    base.OUT_NAME="Fairy2iOS-FairyTail2-KTGL-CoherentConfig-NoFallback.ipa"
    try: report=base.make(source,source_report,repo,output)
    finally:
        base.patch_main=ROOT_PATCH
        base.verify_main=verify_main
    proof=report["guest_root_5g_patch"]["coherent_ktgl_shared_capacity"]
    report.update({
        "method":"coherent KTGL shared 2GiB config field, original consumer loads, 5GiB root; NO guest read/codec signal fallback",
        "coherent_ktgl_shared_capacity":proof,
        "compiled_guest_reader_codec_traps":0,
        "guest_g1t_g1s_untouched":True,
        "no_shader_recompile":True,
        "no_gameplay_claim":True,
    })
    report_path=output/"ktgl-coherent-report.json"
    report_path.write_text(json.dumps(report,indent=2)+"\n")
    print("KTGL coherent candidate:",report["output_ipa_sha256"],
          "original FDATA and shaders untouched; requires real-device test",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-ipa",type=Path,required=True)
    p.add_argument("--source-report",type=Path,required=True)
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    make(a.source_ipa,a.source_report,a.repo.resolve(),a.output)
