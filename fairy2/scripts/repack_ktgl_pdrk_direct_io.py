#!/usr/bin/env python3
"""Global PDRK cache compatibility repack, no shader or parser patch.

The real iPhone log from 45177345329 shows:
  system FDATA PDRK header high word 0x2fe179; the next six reads total
  exactly 0x2fe179. The authentic G1T at 0x2fe0f0 ends there, and G1S
  0x2d3a0 is also inside that preload. Ordinary offset reads of other
  IDRKs complete. The previous synthetic reader recovery failed again.
The working upstream Romance of the Three Kingdoms 8 Remake PDRK
header is PDRK0000 + u64 0x10. Expose that same header shape while keeping
all original offsets and bytes after byte 15. This is a candidate, not
an assertion that the missing cache metadata cause is proved.
"""
from __future__ import annotations
import argparse,hashlib,json,struct,sys
from pathlib import Path
import repack_ktgl_coherent_config as coherent

base=coherent.base
HEADER=Path(__file__).resolve().parent/"ktgl_pdrk_no_preload.h"
OUT_NAME="Fairy2iOS-FairyTail2-PDRK-DirectIO.ipa"
SOURCE_SITES={
 0x612120:"a0050054",0x6e7bb0:"81780054",
 0xc09728:"000840f9",0xc0962c:"880200cb",
 0xc107d8:"f40319aa",0xc11f54:"880640f9",
 0xc11b80:"08a440a9",0xc11f9c:"e00313aa",
 0xc0ef8c:"e9e30191",0xc0f0d4:"e0031f2a",
}
def original_parsers(exe,stamp):
    coherent.verify_main(exe,stamp)
    _,raw=base.main_sections(exe)
    for site,opcode in SOURCE_SITES.items():
        base.require(raw[site:site+4].hex()==opcode,
          f"original guest code not restored at main+0x{site:x}")

def verify_source():
    from probe_resource_origin import Rom,Range,ROOT,records,rdx,pointer,IDRK
    rom=Rom(Range())
    result={"romfs":rom.info,"archives":{},"resources":{}}
    for file,expected in (("0x38f972af.fdata",0x2fe179),
                           ("0x8baaa1ce.fdata",0x2ff648)):
        paths=rom.basename(file)
        base.require(len(paths)==1,"FDATA identity not unique")
        path=paths[0]
        raw=rom.at(path,0,16)
        magic,head,extent=struct.unpack("<8sII",raw)
        base.require(magic==b"PDRK0000" and head==16 and extent==expected
            and 16<extent<=rom.files[path]["size"],
            "Actual Drive header differs from failing device")
        normalized=raw[:12]+bytes(4)
        base.require(normalized==b"PDRK0000"+struct.pack("<Q",16),
                     "Reference header not reproduced")
        result["archives"][file]={"source_header_hex":raw.hex(),
              "reference_header_hex":normalized.hex(),
              "preload_extent":extent,"file_size":rom.files[path]["size"]}
    idx=rom.get(ROOT+"system.rdb")
    pointers=rdx(rom.get(ROOT+"system.rdx"))
    for r in records(idx):
        if r["file"] not in (0xfb9ebd24,0xac9ed13e):continue
        base.require(r["flags"]&0x20000,"Resource must be an external IDRK")
        loc=pointer(idx[r["data"]:r["offset"]+r["size"]])
        target=pointers[loc["marker"]]["file"]
        base.require(target=="0x38f972af.fdata","Unexpected FDATA for resource")
        entry=rom.at(rom.basename(target)[0],loc["offset"],IDRK.size)
        m,es,cs,plain,par,fid,typ,fl=IDRK.unpack(entry)
        base.require(m==b"IDRK0000" and es==loc["size"]
             and fid==r["file"] and typ==r["type"] and plain==r["plain"]
             and 0<cs<=es-IDRK.size and ((fl>>20)&63)==4,
             "Native archive pointer does not identify exact original record")
        base.require(loc["offset"]>=16 and loc["offset"]+es<=
             result["archives"][target]["preload_extent"],
             "Failing resource was not in preloaded prefix")
        result["resources"][hex(fid)]={"archive":target,"record_offset":loc["offset"],
            "record_bytes":es,"plain_bytes":plain,"mode":4,
            "identity_verified":True,"inside_preloaded_prefix":True}
    base.require(set(result["resources"])=={"0xfb9ebd24","0xac9ed13e"},
                 "Missing both real resource pointers")
    return result

def patch_fs(repo):
    fs=repo/"engine/dm/host/hle_fs.c"
    text=fs.read_text()
    include='#include "save_sync.h"'
    anchor="    *out = got;\n    if (g_fslog)"
    base.require(text.count(include)==1 and text.count(anchor)==1
                 and "FAIRY2_PDRK_DIRECT_IO" not in text,
                 "Pinned HLE read hook differs")
    # The helper is pasted, so the generated Xcode target does not depend on
    # an untracked header or an extra build-search path.
    text=text.replace(include,include+"\n"+HEADER.read_text(),1)
    patch=r'''
    /* FAIRY2_PDRK_DIRECT_IO -- virtual header only. ReadFile returns
     * the original byte count and ordinary IDRK contents; no writes to RomFS.
     * Only a real PDRK header with a valid preload extent can be normalized. */
    if (IMG_H(h) && off>=0 && (uint64_t)off<16 && got &&
        (uint64_t)got>12-((uint64_t)off<12?(uint64_t)off:12)) {
        const img_ent *ent=&g_mnt[IMG_M(h)].img->e[IMG_K(h)];
        unsigned char head[16];
        int have=0;
        if (ent->b>=sizeof head) {
            if (off==0 && got>=sizeof head) {
                memcpy(head,buf,sizeof head); have=1;
            } else {
                size_t hn=0;
                while(hn<sizeof head) {
                    ssize_t n=pread(fd,head+hn,sizeof head-hn,base+(int64_t)hn);
                    if(n<0 && errno==EINTR)continue;
                    if(n<=0)break;
                    hn+=(size_t)n;
                }
                have=(hn==sizeof head);
            }
        }
        uint32_t preload=have?f2_pdrk_preload_extent(head,ent->b):0;
        if(preload) {
            dm_guest_write_prepare(buf,got);
            size_t n=f2_pdrk_hide_preload(head,ent->b,(uint64_t)off,buf,got);
            static _Atomic unsigned reported;
            if(n && atomic_fetch_add(&reported,1)<128)
                LOG("FAIRY2_PDRK_DIRECT_IO entry=%u original_preload=%#x header=0x10 offsets_unchanged=1 got=%#zx",
                    (unsigned)IMG_K(h),preload,got);
        }
    }
'''
    text=text.replace(anchor,patch+"    *out = got;\n    if (g_fslog)",1)
    fs.write_text(text)
    # The guest functions are untouched. No crash.c resource recovery installed.
    crash=(repo/"engine/dm/host/crash.c").read_text()
    base.require("FAIRY2_AUTHENTIC_DUAL_NATIVE_SOURCE" not in crash and
        "FAIRY2_KTGL_TRANSACTION_TRACE_ONLY" not in crash,
        "Previous synthetic reader / signal instrumentation is still present")

def make(source,source_report,repo,out):
    proof=verify_source()
    patch_fs(repo)
    verify=coherent.verify_main
    # Avoid recursion: save original and wrap with explicit opcode verification.
    def check(exe,stamp):
        verify(exe,stamp)
        _,raw=base.main_sections(exe)
        for at,word in SOURCE_SITES.items():
            base.require(raw[at:at+4].hex()==word,
                f"Original parser/reader opcode changed main+0x{at:x}")
    coherent.verify_main=check
    try:
        report=coherent.make(source,source_report,repo,out)
    finally:
        coherent.verify_main=verify
    old=out/report["output_ipa"]
    new=out/OUT_NAME
    old.rename(new)
    report.update({"output_ipa":OUT_NAME,
        "method":"Reference KTGL PDRK header without optional preload; all real IDRK offsets preserved; native game resource path",
        "pdrk_direct_io_candidate":True,
        "pdrk_preload_extension_zeroed":True,
        "pdrk_reference_header_hex":"5044524b303030301000000000000000",
        "pdrk_file_offsets_and_idrk_bytes_unchanged":True,
        "original_guest_resource_opcodes":{hex(k):v for k,v in SOURCE_SITES.items()},
        "no_per_resource_fallback":True,"no_guest_parser_traps":True,
        "source_archive_proof":proof,"gameplay_verified":False,
        "external_romfs_aoc_unchanged":True,
        "host_recompiled":True,"game_shaders_recompiled":False})
    (out/"ktgl-pdrk-direct-io-report.json").write_text(json.dumps(report,indent=2)+"\n")
    # Only the new report describes the renamed output.
    (out/"ktgl-coherent-report.json").unlink(missing_ok=True)
    (out/"global-resource-va-report.json").unlink(missing_ok=True)
    print("FAIRY2 PDRK DIRECT IO CANDIDATE",report["output_ipa_sha256"],
          "requires actual iPhone validation",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-ipa",type=Path,required=True)
    p.add_argument("--source-report",type=Path,required=True)
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    make(a.source_ipa,a.source_report,a.repo.resolve(),a.output)
