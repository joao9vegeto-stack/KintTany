#!/usr/bin/env python3
"""G1S native reader proof, not a playable-game claim.
Keep the original eleven G1T probes and one-shot G1T parser recovery.
Add only seven original AArch64 conditional branches. No shader recompilation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import repack_resource_stages as stage

NEW_SITES=(
 (0x6e7bb0,'81780054',0x6e8ac0,'ne', 'g1s-first-184-byte-read-short'),
 (0x6e7bc4,'60220054',0x6e8010,'eq', 'g1s-g2s-magic-valid'),
 (0x6e7bd4,'61770054',0x6e8ac0,'ne','g1s-alternate-header-invalid'),
 (0x6e80f4,'614e0054',0x6e8ac0,'ne','g1s-additional-header-short-read'),
 (0x6e81cc,'a04700b4',0x6e8ac0,'cbz0','g1s-object-allocator-null'),
 (0x6e8230,'e1430054',0x6e8aac,'ne','g1s-body-short-read'),
 (0x1dbdcac,'c00200b4',0x1dbdd04,'cbz0','g1s-native-parser-null'),
)
assert len(stage.TRACE_SITES)==11
stage.TRACE_SITES=stage.TRACE_SITES+NEW_SITES
assert len(stage.TRACE_SITES)==18
old_source=stage.host_trace_source

def host_trace_source():
    src=old_source()
    anchor="  uint64_t x0, x8, x25, x27, lr, cpsr;"
    assert src.count(anchor)==1
    src=src.replace(anchor,"  uint64_t x0, x8, x22, x25, x27, lr, cpsr;\n  unsigned char g1s_first24[24];")
    anchor="    e->x0 = x0; e->x8 = x8; e->x25 = x25; e->x27 = x27;"
    assert src.count(anchor)==1
    src=src.replace(anchor,
      "    e->x0 = x0; e->x8 = x8; e->x22 = uc->uc_mcontext->__ss.__x[22]; e->x25 = x25; e->x27 = x27;\n"
      "    if (off == 0x6e7bb0ULL) {\n"
      "      const unsigned char *p=(const unsigned char *)(uintptr_t)(uc->uc_mcontext->__ss.__fp-0xc0ULL);\n"
      "      for (unsigned k=0; k<24; ++k) e->g1s_first24[k]=p[k];\n"
      "    }")
    anchor="    if (k > 0 && (size_t)k < sizeof buf) write(2, buf, (size_t)k);\n  }\n}\n"
    assert src.count(anchor)==1
    src=src.replace(anchor, r'''    if (k > 0 && (size_t)k < sizeof buf) write(2, buf, (size_t)k);
    if (fairy2_stage_specs[e->slot].off == 0x6e7bb0ULL) {
      static const char hexdigits[]="0123456789abcdef";
      char hex[49];
      for (unsigned j=0;j<24;++j) {
        hex[2*j]=hexdigits[e->g1s_first24[j]>>4];
        hex[2*j+1]=hexdigits[e->g1s_first24[j]&15];
      }
      hex[48]=0;
      k=snprintf(buf,sizeof buf,
        "[dm] FAIRY2_G1S_READER first_read=%llu expected=184 guest_reader=%#llx first24=%s\n",
        (unsigned long long)e->x0,(unsigned long long)e->x22,hex);
      if (k > 0 && (size_t)k < sizeof buf) write(2,buf,(size_t)k);
    }
  }
}
''')
    assert "FAIRY2_G1S_READER first_read" in src
    return src
stage.host_trace_source=host_trace_source


# Cross-layer reader proof: POSIX RomFS-image reads versus the G1S virtual
# reader return. Avoid guessing whether the failure is FS, zlib, or cursor.
def patch_host_fs_trace(path:Path):
    src=path.read_text()
    target='HLE_FORCE("_ZN2nn2fs8ReadFileEPmNS0_10FileHandleElPvm", "fsp-srv → pread(2)", Result, h_fs_ReadFile, size_t *out, uint64_t h, int64_t off, void *buf, size_t sz) { dm_thread_service_request();'
    stage.base.require(src.count(target)==1, "Pinned NXNative ReadFile anchor changed")
    stage.base.require("FAIRY2_FDATA_IO_PROOF" not in src, "host FS already patched")
    before=src[:src.index(target)]
    tail=src[src.index(target):]
    next_fn='HLE_FORCE("_ZN2nn2fs9WriteFileENS0_10FileHandleElPKvmRKNS0_11WriteOptionE"'
    stage.base.require(next_fn in tail, "ReadFile end not found")
    read,remain=tail.split(next_fn,1)
    stage.base.require(read.count("    *out = got;\n")==1, "ReadFile count assignment changed")
    read=read.replace("    *out = got;\n", r'''    *out = got;
    /* Fairy2iOS only: observed RDB source files in the exact external
       DMROMFS1 image (verified entries 12943 and 13660, stable SHA). */
    if (IMG_H(h) && (IMG_K(h) == 12943 || IMG_K(h) == 13660)) {
        fairy2_fdata_io_record(h, off, requested, sz, got, base,
                              g_mnt[IMG_M(h)].img->e[IMG_K(h)].b,
                              got >= 8 ? buf : NULL);
    }
''',1)
    stage.base.require(read.count('            return err_res("pread", "fd"); }')==1,
                       "Host ReadFile error path differs")
    read=read.replace('            return err_res("pread", "fd"); }',
        '            if (IMG_H(h) && (IMG_K(h)==12943 || IMG_K(h)==13660))\n'
        '                LOG("[dm] FAIRY2_FDATA_IO_ERROR entry=%llu off=%lld got=%zu errno=%d",\n'
        '                    (unsigned long long)IMG_K(h), (long long)off, got, errno);\n'
        '            return err_res("pread", "fd"); }')
    old='    size_t got = 0; int reprep = 0, fd = (int)h; int64_t base = 0;'
    stage.base.require(read.count(old)==1, "ReadFile input size binding changed")
    read=read.replace(old,
         '    size_t requested = sz;\n'+old,1)
    block=r'''
/* FAIRY2_FDATA_IO_PROOF: runtime source IO correlated with native G1S parser.
 * No ROMFS contents, shader files, guest code, filesystem result or offset
 * are modified. This is NOT a gameplay fix. */
struct fairy2_fdata_event {
    uint64_t seq, h, entry, off, wanted, clipped, got, base, entry_size, first8;
};
#define FAIRY2_FDATA_RING 512u
static struct fairy2_fdata_event fairy2_fdata_events[FAIRY2_FDATA_RING];
static uint64_t fairy2_fdata_seq;
static void fairy2_fdata_io_record(uint64_t h, int64_t off,
                                   size_t wanted, size_t clipped, size_t got,
                                   int64_t base, uint64_t entry_size,
                                   const void *content) {
    const uint64_t seq=__atomic_add_fetch(&fairy2_fdata_seq, 1, __ATOMIC_RELAXED);
    struct fairy2_fdata_event *e=&fairy2_fdata_events[seq & (FAIRY2_FDATA_RING-1)];
    e->h=h; e->entry=IMG_K(h); e->off=(uint64_t)off;
    e->wanted=wanted; e->clipped=clipped; e->got=got;
    e->base=(uint64_t)base; e->entry_size=entry_size;
    e->first8=0;
    if (content) memcpy(&e->first8, content, 8);
    __atomic_store_n(&e->seq, seq, __ATOMIC_RELEASE);
    if (wanted && !got) LOG("[dm] FAIRY2_FDATA_IO_ZERO entry=%llu off=%lld wanted=%zu clipped=%zu len=%llu",
                           (unsigned long long)e->entry, (long long)off,
                           wanted, clipped, (unsigned long long)entry_size);
}
void fairy2_fdata_probe_dump(void) {
    uint64_t last=__atomic_load_n(&fairy2_fdata_seq, __ATOMIC_ACQUIRE);
    uint64_t first=last>128?last-128:1;
    LOG("[dm] FAIRY2_FDATA_IO_HISTORY last %llu of %llu reads targeting source FDATA entries 12943/13660",
        (unsigned long long)(last>=first?last-first+1:0), (unsigned long long)last);
    for(uint64_t seq=first; seq<=last && seq>0; ++seq) {
        struct fairy2_fdata_event *e=&fairy2_fdata_events[seq & (FAIRY2_FDATA_RING-1)];
        if (__atomic_load_n(&e->seq, __ATOMIC_ACQUIRE)!=seq) continue;
        LOG("[dm] FAIRY2_FDATA_IO #%llu entry=%llu off=%lld wanted=%llu clipped=%llu got=%llu base=%llu filelen=%llu data_first8=%016llx",
            (unsigned long long)seq, (unsigned long long)e->entry,
            (long long)e->off, (unsigned long long)e->wanted,
            (unsigned long long)e->clipped, (unsigned long long)e->got,
            (unsigned long long)e->base, (unsigned long long)e->entry_size,
            (unsigned long long)e->first8);
    }
}
'''
    path.write_text(before+block+read+next_fn+remain)
    stage.base.require("FAIRY2_FDATA_IO_PROOF" in path.read_text(),
                       "FS instrumentation not written")

def patch_host_crash_io(path:Path):
    src=path.read_text()
    anchor="    if (sig == SIGTRAP) fairy2_stage_dump();"
    stage.base.require(src.count(anchor)==1, "Stage dump anchor missing")
    # The existing 18 exact original branch decisions remain unchanged.
    src=src.replace(anchor,"    if (sig == SIGTRAP) { fairy2_stage_dump(); fairy2_fdata_probe_dump(); }")
    anchor2="static void on_crash(int sig, siginfo_t *si, void *uc_) {"
    stage.base.require(src.count(anchor2)==1, "Crash entry changed")
    src=src.replace(anchor2,"extern void fairy2_fdata_probe_dump(void);\n"+anchor2,1)
    path.write_text(src)

def make(source:Path,report:Path,repo:Path,out:Path):
    base=stage.base
    base.require((repo/'.upstream-ref').read_text().strip()==base.hook.ENGINE_PIN,"wrong pinned NXNative")
    stage.patch_host_crash(repo/'engine/dm/host/crash.c')
    patch_host_crash_io(repo/'engine/dm/host/crash.c')
    patch_host_fs_trace(repo/'engine/dm/host/hle_fs.c')
    base.patch_main=stage.trace_patch_main
    base.verify_main=stage.trace_verify_main
    base.OUT_NAME='Fairy2iOS-FairyTail2-G1S-FDATA-IOProbe.ipa'
    result=base.make(source,report,repo,out)
    result.update({
      "resource_stage_trace":True,
      "fdata_io_proof":True,
      "probe_entries": [12943, 13660],
      "device_boot_verified":False,
      "branch_emulation":"exact AArch64 original 18 conditional predicates",
      "branch_trace_sites":18,
      "g1t_fallback_preserved":True,
      "g1s_factory":"main+0x1dbdc14",
      "g1s_parser":"main+0x6e7b60",
      "g1s_header_read":"virtual [vtable+0x20] requests 184 bytes",
      "g1s_type":"0x7bcd279f",
      "g1s_hash":"0xac9ed13e",
      "g1s_full_original_sha256":"edb3bceed3c426cfe5b851d78f2e7f56168abe8ac5d6aac3a6927bdaf6e3535a",
      "device_boot_verified":False,
      "not_a_gameplay_fix":True,
      "reason":"trace whether G1S rejects 184-byte stream, valid header, body, allocator or parser",
    })
    (out/'g1s-readertrace-report.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source-ipa',required=True,type=Path)
    p.add_argument('--source-report',required=True,type=Path)
    p.add_argument('--repo',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    make(a.source_ipa,a.source_report,a.repo.resolve(),a.output)
