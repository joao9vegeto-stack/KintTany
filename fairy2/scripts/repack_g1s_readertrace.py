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
    anchor="    if (k > 0 && (size_t)k < sizeof buf) write(2, buf, (size_t)k);\n  }\n}\n'''"
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
''' ''')
    assert "FAIRY2_G1S_READER first_read" in src
    return src
stage.host_trace_source=host_trace_source

def make(source:Path,report:Path,repo:Path,out:Path):
    base=stage.base
    base.require((repo/'.upstream-ref').read_text().strip()==base.hook.ENGINE_PIN,"wrong pinned NXNative")
    stage.patch_host_crash(repo/'engine/dm/host/crash.c')
    base.patch_main=stage.trace_patch_main
    base.verify_main=stage.trace_verify_main
    base.OUT_NAME='Fairy2iOS-FairyTail2-G1S-ReaderTrace.ipa'
    result=base.make(source,report,repo,out)
    result.update({
      "resource_stage_trace":True,
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
