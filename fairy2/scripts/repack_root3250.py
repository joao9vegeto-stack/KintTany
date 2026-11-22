#!/usr/bin/env python3
"""Fairy2iOS: fix the second, iPhone-proven KTGL memory-region overrun.

The 3 GiB guest address reservation at 0x364000000 ends at 0x424000000.
An inner allocator's 2 GiB span starts at 0x3a5800000 and ends at
0x425800000; its split-node store at main+0x227bd9c touched 0x4257d9e00
(23.85 MiB outside the outer reservation), after nn::os::ResultInvalidParameter.
These addresses are from the A19 Pro log, not from the virtual Mac GPU.
Raise ALL five verified parent-region MOVZs from 3 to 3.25 GiB; keep the
1.25 GiB KTGL subregion size, the prior heap and alignment changes, as well
as the existing iOS host and Metal library. We do not NOP the crash site.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import repack_align64 as base

SOURCE_RUN=44986770915
SOURCE_SHA="3d2b464701d72eb9abf2a9aaa42e8d59f3cef3efe33203710e515bddf7b315a8"
SOURCE_NAME="Fairy2iOS-FairyTail2-KTGL-1250MiB-region-cap.ipa"
OUTPUT_NAME="Fairy2iOS-FairyTail2-KTGL-3250MiB-root-region.ipa"
PREVIOUS_SIZE=0xc0000000  # 3 GiB, previous five cuts
FIXED_SIZE=0xd0000000     # 3.25 GiB, five site-consistent cuts
SDK_NODE_AREA=0x3e00000  # 62 MiB NXNative SDK patch
ALIAS_SIZE=0xe0000000    # 3.5 GiB iPhone alias
ROOT_START=0x364000000
INNER_START=0x3a5800000
INNER_SIZE=0x80000000
CRASH_ADDR=0x4257d9e00
CRASH_PC=0x227bd9c
METAL_SHA="ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b"
# Every row is bound to the exact rewritten main and the last Mac-tested IPA.
# Check all windows first, because the two final context windows overlap.
MOVZ=(
 (0x5f1b9c,"0900b8d2","0900bad2","ec6da51607fd596ab78a5db9c5cc33ff0ae0afb0892da86f1324afe1ff7d0954"),
 (0x1d700bc,"0900b8d2","0900bad2","6403877418818685c6597d0cf6ddecf3a514b01beb70685c6939b7427c57f517"),
 (0x225de0c,"0900b8d2","0900bad2","41e10f92799523faf4cac10d88b0c6ed615111d191c147177dcf8e06bf735463"),
 (0x2295a44,"0900b8d2","0900bad2","14af074ec9e362a66a3037a5f5846f3371ad6b4ad70c24e614604d1f2028de3f"),
 (0x2295a50,"0100b8d2","0100bad2","33f308fa4fb5641df2e87dd91f54f1bc6cbcb833e58ddf8c0e515f1ebbf00e9d"),
)
PREVIOUS=(
 (0x2295a88,"1300a152","128 MiB SDK heap"),
 (0x21b6a74,"2200a052","64 KiB GPU allocation alignment"),
 (0x21b6924,"0880a2d2","KTGL 1.25 GiB region producer"),
 (0x21b6954,"1980a2d2","KTGL 1.25 GiB region accounting"),
)

def memory_geometry():
    """Exact independent bounds from the iPhone crash, not a hypothetical OOM."""
    end_old=ROOT_START+PREVIOUS_SIZE
    end_new=ROOT_START+FIXED_SIZE
    end_inner=INNER_START+INNER_SIZE
    end_alias=0x360000000+ALIAS_SIZE
    base.require(ROOT_START==0x360000000+0x4000000,"SDK node placement differs")
    base.require(end_old < CRASH_ADDR < end_inner,
                 "crash must be outside the old root but inside the inner allocator")
    base.require(end_inner-end_old==0x1800000,
                 "the observed inner allocator overrun is not exactly 24 MiB")
    base.require(CRASH_ADDR-end_old==0x17d9e00,
                 "iPhone crash address differs from audit")
    base.require(end_inner<end_new<end_alias,
                 "3.25 GiB root must fully contain 2 GiB child and stay inside alias")
    base.require(FIXED_SIZE+SDK_NODE_AREA<ALIAS_SIZE,
                 "SDK node area plus root must fit iPhone guest alias")
    base.require(FIXED_SIZE-PREVIOUS_SIZE==0x10000000,
                 "root expansion exceeds approved extra 256 MiB of VIRTUAL space")
    return {
        "old_root_start":hex(ROOT_START),"old_root_end":hex(end_old),
        "new_root_end":hex(end_new),"inner_region_start":hex(INNER_START),
        "inner_region_end":hex(end_inner),"alias_end":hex(end_alias),
        "crash_site":f"main+0x{CRASH_PC:x}","crash_address":hex(CRASH_ADDR),
        "unreserved_bytes_before":CRASH_ADDR-end_old,
        "inner_overrun_bytes_before":end_inner-end_old,
        "alias_headroom_bytes_after":end_alias-end_new,
        "virtual_increase_bytes":FIXED_SIZE-PREVIOUS_SIZE,
    }

def patch_root_bytes(guest:bytes)->bytes:
    geometry=memory_geometry()
    base.require(len(guest)>max(off for off,*_ in MOVZ)+40,
                 "guest main truncated or wrong game")
    for off,old,new,context in MOVZ:
        base.require(guest[off:off+4]==bytes.fromhex(old),
                     f"guest main+0x{off:x} is not the five-cut v458752 build")
        base.require(hashlib.sha256(guest[off-24:off+40]).hexdigest()==context,
                     f"guest main+0x{off:x} fingerprint does not match original A19 Pro IPA")
    for off,opcode,desc in PREVIOUS:
        base.require(guest[off:off+4]==bytes.fromhex(opcode),
                     f"previous repair lost: {desc} at main+0x{off:x}")
    amended=bytearray(guest)
    for off,old,new,context in MOVZ:
        amended[off:off+4]=bytes.fromhex(new)
    base.require(sum(a!=b for a,b in zip(guest,amended))==5,
                 "unexpected changes outside five approved AArch64 MOVZ bytes")
    for off,opcode,desc in PREVIOUS:
        base.require(amended[off:off+4]==bytes.fromhex(opcode),
                     f"repack changed preserved patch {desc}")
    return bytes(amended)

def patch_framework(framework:Path):
    offset,guest=base.embedded_main(framework)
    changed=patch_root_bytes(guest)
    with framework.open("r+b") as f:
        f.seek(offset)
        base.require(f.read(len(guest))==guest,"embedded game changed during patch")
        f.seek(offset)
        f.write(changed)
    return {
        "old_guest_sha256":hashlib.sha256(guest).hexdigest(),
        "new_guest_sha256":hashlib.sha256(changed).hexdigest(),
        "section_size":len(changed),"changed_bytes":5,
        "five_root_movz_verified":True,
        "offsets":[f"main+0x{off:x}" for off,*_ in MOVZ],
        "new_root_virtual_size":FIXED_SIZE,
        "parent_region_geometry":memory_geometry()
    }

def check_framework(framework:Path,report:dict):
    _,guest=base.embedded_main(framework)
    base.require(len(guest)==report["section_size"] and
                 hashlib.sha256(guest).hexdigest()==report["new_guest_sha256"],
                 "signed IPA guest does not equal exact five-opcode repair")
    for off,old,new,context in MOVZ:
        base.require(guest[off:off+4]==bytes.fromhex(new),
                     f"new root cap absent at main+0x{off:x}")
    for off,opcode,desc in PREVIOUS:
        base.require(guest[off:off+4]==bytes.fromhex(opcode),
                     f"prior KTGL repair lost: {desc}")
    return True

def make(source:Path,output:Path,report:Path):
    base.SOURCE_RUN=SOURCE_RUN
    base.SOURCE_SHA=SOURCE_SHA
    base.SOURCE_NAME=SOURCE_NAME
    base.OUTPUT_NAME=OUTPUT_NAME
    base.patch_framework=patch_framework
    base.check_framework=check_framework
    rec=base.make(source,output,report)
    base.require(rec["source_ipa_sha256"]==SOURCE_SHA and
                 rec["source_run_id"]==SOURCE_RUN,
                 "wrong IPA was used as source")
    audit=rec.pop("arena_alignment_instruction_audit",None)
    base.require(isinstance(audit,dict) and audit["changed_bytes"]==5,
                 "expected five site-consistent root changes")
    for stale in (
        "alloc_alignment_before_bytes","alloc_alignment_after_bytes",
        "five_region_cut_movs_preserved","aligned_arena_32mib_fix_verified"
    ):
        rec.pop(stale,None)
    rec.update({
        "method":"Full original iPhone crash trace, 5 MOVZ guest-only corrections: outer virtual root 3 -> 3.25 GiB",
        "original_crash_pc":"main+0x227bd9c",
        "original_crash_address":"0x4257d9e00",
        "guest_root_patch":audit,
        "guest_root_previous_size":PREVIOUS_SIZE,
        "guest_root_new_size":FIXED_SIZE,
        "prior_ktgl_1_25g_capacity_preserved":True,
        "prior_64k_alignment_preserved":True,
        "prior_128m_heap_preserved":True,
        "first_32mib_arena_crash_resolved_on_iphone":True,
        "second_root_bounds_issue_statically_validated":True,
        "new_ipa_runtime_verified_on_iphone":False,
        "fps_options_in_launcher":[30,60],
        "fps_actual_unlocked_verified":False,
        "a_b_toggle_runtime_verified":False,
        "no_shader_rebuild":True,
        "no_native_host_rebuild":True,
        "original_metal_lib_sha256":METAL_SHA,
    })
    report.write_text(json.dumps(rec,indent=2)+"\n")
    print("[Fairy2iOS] 3.25 GiB outer root (five AArch64 constants), original Metal intact. IPA",
          rec["output_ipa"],"size",rec["output_size_bytes"],"sha256",rec["output_sha256"],flush=True)
    return rec

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    make(args.source,args.output,args.report)
