#!/usr/bin/env python3
"""Fairy2iOS: source-only correction of KTGL direct-reader short returns.

The pinned original reader can return 0 before its inflater runs; previous
libz-inflater-only fallback could not correct that. Preserve that fallback,
and on a *zero-return from the original mode4 direct stream only*, use the
validated original in-memory RDB packet to populate the existing reader cache.
Never supply generated G1T/G1S resources or fake successes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import repack_mode4_nativez as native

base=native.base
BRK=native.BRK
DIRECT = {
    0xc11b80: bytes.fromhex("08a440a9"), # ldp x8,x9,[x0,#8]
    0xc11f9c: bytes.fromhex("e00313aa"), # mov x0,x19
}

def patch_guest(exe:Path, oldreport:dict):
    stamp=native.patch_original_codec_guest(exe,oldreport)
    pieces,raw=base.main_sections(exe)
    x0=pieces["x0"]
    work=bytearray(raw)
    with exe.open("r+b") as file:
        for at,op in DIRECT.items():
            base.require(at+4<=x0["size"] and raw[at:at+4]==op,
                         f"pinned native 2-byte KTGL reader opcode drift at main+0x{at:x}")
            file.seek(x0["offset"]+at)
            base.require(file.read(4)==op,"direct reader changed during repack")
            file.seek(x0["offset"]+at)
            file.write(BRK)
            work[at:at+4]=BRK
    out,actual=base.main_sections(exe)
    base.require(actual==bytes(work),"direct reader modified non-site guest data")
    base.require(pieces["w"]["data"]==out["w"]["data"] and
                 pieces["x1"]["data"]==out["x1"]["data"],
                 "guest RO/data or signed x18 gate section modified")
    stamp["after_sha256"]=hashlib.sha256(actual).hexdigest()
    stamp["x0_after_sha256"]=hashlib.sha256(out["x0"]["data"]).hexdigest()
    stamp["original_direct_reader"]={
        f"main+0x{p:x}":{"source_opcode":op.hex(),"signal_guard":BRK.hex()}
        for p,op in DIRECT.items()
    }
    stamp["direct_codec_primary"]="unchanged guest stream; native only on zero"
    return stamp

def verify_guest(exe:Path, stamp:dict):
    native.verify_original_codec_guest(exe,stamp)
    _,data=base.main_sections(exe)
    base.require(len(stamp.get("original_direct_reader") or {})==2,
                 "direct reader proof missing")
    for at in DIRECT:
        base.require(data[at:at+4]==BRK, f"direct reader trap lost at main+0x{at:x}")

def patch_host_crash(path:Path, repo:Path):
    native.patch_host_crash(path,repo)
    host=path.read_text()
    addon=(repo/"fairy2/scripts/ktgl_direct_reader_recovery_host.h").read_text()
    anchor="static void on_crash(int sig, siginfo_t *si, void *uc_) {"
    hook="    if (sig == SIGTRAP && f2_zlib_fail_path_trap(uc)) return;"
    for marker in ("FAIRY2_KTGL_DIRECT_MODE4_SOURCE_RECOVERY",
                   "f2_direct_recover_original_block(",
                   "f2_zlib_original_chunk(cache, F2_ZLIB_MAX_OUT",
                   "original==0 && f2_direct_recover_original_block(&snapshot)",
                   "vt == (uint64_t)(uintptr_t)module->base + 0x2a64b50u"):
        base.require(marker in addon, "direct original-source guard missing: "+marker)
    base.require(host.count(anchor)==1 and host.count(hook)==1 and
                 "FAIRY2_KTGL_DIRECT_MODE4_SOURCE_RECOVERY" not in host,
                 "pinned source original crash handler changed")
    host=host.replace(anchor,addon+"\n"+anchor,1)
    host=host.replace(hook,
         "    if (sig == SIGTRAP && f2_direct_reader_trap(uc)) return;\n"+hook,1)
    path.write_text(host)

def make(source:Path,source_report:Path,repo:Path,out:Path):
    base.require((repo/".upstream-ref").read_text().strip()==base.hook.ENGINE_PIN,
                 "NXNative pinned engine drift")
    patch_host_crash(repo/"engine/dm/host/crash.c",repo)
    base.patch_main=patch_guest
    base.verify_main=verify_guest
    base.OUT_NAME="Fairy2iOS-FairyTail2-OriginalMode4-ReaderRecovery.ipa"
    data=base.make(source,source_report,repo,out)
    data.update({
        "native_failure_path":"main+0xc11b60 / zero at main+0xc11f9c",
        "original_header_parser":"main+0xc121a8 (mode4 2B encoded length +8)",
        "native_original_packet_only":True,
        "original_mode4_vtable":"main+0x2a64b50",
        "guest_parser_unchanged":True,
        "no_synthetic_g1t_g1s":True,
        "no_repeated_reads":True,
        "only_when_read_returns_zero":True,
        "fallback_requires_complete_RFC1950_adler32":True,
        "preserve_guest_compressed_and_decoded_cursors":True,
        "no_game_assets_modified":True,
        "original_metal_shaders_preserved":True,
        "number_of_shaders_recompiled":0,
        "runtime_tested_on_iphone":False,
        "not_a_gameplay_fix":True,
    })
    (out/"mode4-direct-reader-report.json").write_text(
        json.dumps(data,indent=2,ensure_ascii=False)+"\n")
    return data

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-ipa",required=True,type=Path)
    p.add_argument("--source-report",required=True,type=Path)
    p.add_argument("--repo",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    x=p.parse_args()
    make(x.source_ipa,x.source_report,x.repo.resolve(),x.output)
