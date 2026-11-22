#!/usr/bin/env python3
"""Fairy Tail 2 IPA-only corrected KTGL virtual arena allocation.

Mac run 44985713638 proved an original 6.17GiB sparse region failed inside
the project's 3GiB region, causing the 32MiB KTGL arena's null base and iPhone
SIGSEGV main+0x21b6dcc at 0x1ebc4. Mac run 44986356916 proved that two
matching capacity loads changed to 1.25GiB produce valid allocated memory,
no SDK ResultInvalidParameter, no original SIGSEGV, reaching Metal init.
Uses last aligned IPA as source; modifies ONLY the two verified AArch64 MOVZs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import repack_align64 as base

SOURCE_RUN=44983552364
SOURCE_SHA="a8945d1b4f940f697df1fabd81fa647f91f5911b169fbbc9ce5882bab2c597fb"
SOURCE_NAME="Fairy2iOS-FairyTail2-64KiB-aligned-allocator.ipa"
OUTPUT_NAME="Fairy2iOS-FairyTail2-KTGL-1250MiB-region-cap.ipa"
PROOF_RUN=44986356916
CAP_UNITS=0x14000000
RESERVED_BYTES=0x50000000
PRIOR_ALIGN_OFF=0x21b6a74
PRIOR_HEAP_OFF=0x2295a88
INSTRUCTIONS=(
 (0x21b6924,"687340f9","0880a2d2",
 "e83b597e858092be0d6e862c1c9493ef5f45de0f8e31b81331cf4b23965720a9"),
 (0x21b6954,"797340f9","1980a2d2",
 "86763694b6662481d434d39f8d384b22956192a244ddf11b893867a5990f1448"),
)

def patch_two_caps(guest:bytes)->bytes:
    require=base.require
    require(len(guest)>max(o[0] for o in INSTRUCTIONS)+40,
            "wrong or truncated Fairy Tail 2 main")
    for off,old,new,context in INSTRUCTIONS:
        require(guest[off:off+4]==bytes.fromhex(old),
                f"wrong guest build opcode at main+0x{off:x}")
        require(hashlib.sha256(guest[off-24:off+40]).hexdigest()==context,
                f"guest function fingerprint at main+0x{off:x} differs")
    require(guest[PRIOR_ALIGN_OFF:PRIOR_ALIGN_OFF+4]==bytes.fromhex("2200a052"),
            "verified previous 64KiB aligned arena patch lost")
    require(guest[PRIOR_HEAP_OFF:PRIOR_HEAP_OFF+4]==bytes.fromhex("1300a152"),
            "verified previous 128MiB heap patch lost")
    for off,old,new,*_ in base.SITES:
        require(guest[off:off+4]==bytes.fromhex(new),
                f"previous 3GiB region patch lost at main+0x{off:x}")
    out=bytearray(guest)
    for off,old,new,context in INSTRUCTIONS:
        out[off:off+4]=bytes.fromhex(new)
    require(sum(a!=b for a,b in zip(guest,out))==8,
            "only eight bytes in two guest instructions may change")
    return bytes(out)

def patch_framework(framework:Path):
    offset,old=base.embedded_main(framework)
    new=patch_two_caps(old)
    with framework.open("r+b") as f:
        f.seek(offset)
        base.require(f.read(len(old))==old,"guest source changed before write")
        f.seek(offset)
        f.write(new)
    return {"original_section_sha256":hashlib.sha256(old).hexdigest(),
            "patched_section_sha256":hashlib.sha256(new).hexdigest(),
            "section_size":len(new),"byte_changes":8,"instruction_count":2,
            "instructions":[{"site":f"main+0x{off:x}","original_opcode":old,
                              "patched_opcode":new,"original_context_sha256":ctx}
                             for off,old,new,ctx in INSTRUCTIONS]}

def check_framework(framework:Path,proof:dict):
    _,guest=base.embedded_main(framework)
    base.require(len(guest)==proof["section_size"] and
                 hashlib.sha256(guest).hexdigest()==proof["patched_section_sha256"],
                 "signed guest image not exactly the approved two-MOVZ modification")
    for off,old,new,ctx in INSTRUCTIONS:
        base.require(guest[off:off+4]==bytes.fromhex(new),
                     "repacked IPA lost corrected KTGL capacity")
    base.require(guest[PRIOR_ALIGN_OFF:PRIOR_ALIGN_OFF+4]==bytes.fromhex("2200a052")
                 and guest[PRIOR_HEAP_OFF:PRIOR_HEAP_OFF+4]==bytes.fromhex("1300a152"),
                 "predecessor corrections modified")
    for off,old,new,*_ in base.SITES:
        base.require(guest[off:off+4]==bytes.fromhex(new),
                     "3GiB region predecessor modified")
    return True

def configure_repack():
    # Reuse exactly the known-good IPA unpacking/signing/CRC/Metal/host checks.
    base.SOURCE_RUN=SOURCE_RUN
    base.SOURCE_SHA=SOURCE_SHA
    base.SOURCE_NAME=SOURCE_NAME
    base.OUTPUT_NAME=OUTPUT_NAME
    base.patch_framework=patch_framework
    base.check_framework=check_framework

def make(source:Path,output:Path,report:Path):
    configure_repack()
    record=base.make(source,output,report)
    base.require(record["output_ipa"]==OUTPUT_NAME and
                 record["source_run_id"]==SOURCE_RUN and
                 record["source_ipa_sha256"]==SOURCE_SHA,
                 "repack inherited wrong source")
    audit=record.pop("arena_alignment_instruction_audit")
    base.require(audit["byte_changes"]==8 and audit["instruction_count"]==2,
                 "capacity audit not the expected two instructions")
    for key in ("alloc_alignment_before_bytes","alloc_alignment_after_bytes",
                "aligned_arena_32mib_fix_verified"):
        record.pop(key,None)
    record.update({
        "project":"Fairy2iOS",
        "method":"Existing IPA, two fingerprint-verified KTGL sparse arena capacity opcodes; no shader/host compile",
        "mac_runtime_proof_run_id":PROOF_RUN,
        "ktgl_original_capacity_units":0x62c00000,
        "ktgl_corrected_capacity_units":CAP_UNITS,
        "ktgl_original_sparse_region_bytes":0x18b000000,
        "ktgl_corrected_sparse_region_bytes":RESERVED_BYTES,
        "capacity_instruction_audit":audit,
        "original_3g_region_cut_preserved":True,
        "heap128_mib_patch_preserved":True,
        "aligned64k_arena_patch_preserved":True,
        "native_host_recompiled":False,
        "game_shaders_recompiled":False,
        "guest_modules_rewritten":False,
        "mac_arena_32mib_valid_verified":True,
        "mac_old_sigsegv_removed_verified":True,
        "mac_graphics_test_blocked_by_virtual_gpu_no_metal4":True,
        "iphone_boot_verified":False,
        "iphone_graphics_verified":False,
    })
    report.write_text(json.dumps(record,indent=2)+"\n")
    print("[Fairy2iOS] KTGL capacity repack verified; signed IPA",OUTPUT_NAME,
          "SHA-256",record["output_sha256"],flush=True)
    return record

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    make(a.source,a.output,a.report)
