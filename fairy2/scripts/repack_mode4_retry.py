#!/usr/bin/env python3
"""Fairy2iOS mode-4 resource-stream bounded retry (original data only).

The verified source IDRK/zlib bytes are intact, and iPhone HLE pread completed
45/45 operations while native G1T and G1S parsers saw an empty stream. This
experiment permits bounded re-reads of the *same* guest virtual reader during
the async producer handoff. It NEVER substitutes hardcoded asset bytes, skips a
parser check, or claims the game is playable without an actual iPhone test.
Only host and 18 exact original branch probes are changed; no shader build.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import repack_g1s_readertrace as reader

stage=reader.stage
base=stage.base
original=stage.host_trace_source

def bounded_retry_source():
    src=original()
    a=src.index('/* FAIRY2 G1T HEADER RESCUE:')
    b=src.index('       (taken ? s->target : s->off + 4);',a)
    b=src.rfind('    uc->uc_mcontext->__ss.__pc =',a,b)
    base.require(b>a,'Original branch tail unavailable')
    # Remove original one-shot synthetic 48-byte G1T injection entirely.
    src=src[:a]+src[b:]
    a=src.index('    /* Both iPhone logs: #76 header fail')
    b=src.index('    uc->uc_mcontext->__ss.__pc = (uint64_t)(uintptr_t)m->base +\\n       (taken ? s->target : s->off + 4);',a)
    src=src[:a]+r'''
    /* FAIRY2_MODE4_ORIGINAL_STREAM_RETRY: neither a G1T override nor a G1S
     * header bypass. The original chunk producer may publish after the
     * reader's first attempt. Retry only a failed *initial* native read,
     * at most 64 times, then preserve the unchanged native failure.
     * Per-thread counters avoid cross-thread state corruption.
     * All accesses to guest parser state are guarded by the exact code site. */
    static __thread unsigned fairy2_g1t_attempts, fairy2_g1s_attempts;
    if (s->off == 0x612120ULL) {
      if (!taken) fairy2_g1t_attempts=0;
      else if (x27 == (uint64_t)(uintptr_t)m->base + 0x2c15c40ULL &&
               fairy2_g1t_attempts < 64) {
        const uint64_t sp=uc->uc_mcontext->__ss.__sp;
        const unsigned char *header=(const unsigned char *)(uintptr_t)(sp+0x50);
        int empty=1;
        for (unsigned k=0;k<28;++k) if(header[k]) { empty=0; break; }
        if (empty) {
          fairy2_g1t_attempts++;
          if (fairy2_g1t_attempts == 1 || fairy2_g1t_attempts == 64)
            LOG("[dm] FAIRY2_MODE4_ORIGINAL_RETRY g1t attempt=%u/64 original header all zero; no synthetic data",fairy2_g1t_attempts);
          for (volatile unsigned spin=0;spin<16384;++spin)
              __asm__ __volatile__("yield" ::: "memory");
          /* Native G1T retry entry restores destination and source reader.
           * w26 retained original parser flags; x23 original reader pointer. */
          uc->uc_mcontext->__ss.__x[2]=uc->uc_mcontext->__ss.__x[26];
          uc->uc_mcontext->__ss.__pc=(uint64_t)(uintptr_t)m->base+0x61210cULL;
          return 1;
        }
      }
    }
    if (s->off == 0x6e7bb0ULL) {
      if (!taken) {
        if (fairy2_g1s_attempts)
          LOG("[dm] FAIRY2_MODE4_ORIGINAL_RETRY g1s recovered after %u attempts using native stream",fairy2_g1s_attempts);
        fairy2_g1s_attempts=0;
      } else if (x0 == 0 && fairy2_g1s_attempts < 64) {
        const uint64_t reader=uc->uc_mcontext->__ss.__x[22];
        if (reader && ((reader & 7)==0)) {
          fairy2_g1s_attempts++;
          if (fairy2_g1s_attempts == 1 || fairy2_g1s_attempts == 64)
            LOG("[dm] FAIRY2_MODE4_ORIGINAL_RETRY g1s attempt=%u/64 first-read=0/184",fairy2_g1s_attempts);
          for (volatile unsigned spin=0;spin<16384;++spin)
              __asm__ __volatile__("yield" ::: "memory");
          /* 6e7b94 reloads vtable[+0x20], then reconstructs the original
           * 184-byte read ABI. x22 remains the exact original reader. */
          uc->uc_mcontext->__ss.__x[8]=*(const uint64_t *)(uintptr_t)reader;
          uc->uc_mcontext->__ss.__pc=(uint64_t)(uintptr_t)m->base+0x6e7b94ULL;
          return 1;
        }
      }
    }
''' +src[b:]
    # Exact run-time invariants; no stale rescue call remains reachable.
    base.require('fairy2_known_g1t' not in src,'obsolete fixed 48B stream remains')
    base.require('fairy2_g1t_recovery_attempted' not in src,'G1T synthetic recovery remains')
    base.require('FAIRY2_MODE4_ORIGINAL_RETRY g1t attempt' in src,'no G1T retry')
    base.require('FAIRY2_MODE4_ORIGINAL_RETRY g1s attempt' in src,'no G1S retry')
    return src

def make(source:Path,report:Path,repo:Path,out:Path):
    base.require((repo/'.upstream-ref').read_text().strip()==base.hook.ENGINE_PIN,
                 'Pinned engine changed')
    stage.host_trace_source=bounded_retry_source
    stage.patch_host_crash(repo/'engine/dm/host/crash.c')
    reader.patch_host_crash_io(repo/'engine/dm/host/crash.c')
    reader.patch_host_fs_trace(repo/'engine/dm/host/hle_fs.c')
    base.patch_main=stage.trace_patch_main
    base.verify_main=stage.trace_verify_main
    base.OUT_NAME='Fairy2iOS-FairyTail2-Mode4-BoundedRetry.ipa'
    result=base.make(source,report,repo,out)
    result.update({
        'mode4_native_retry_enabled':True,
        'g1t_fallback_preserved':False,
        'original_stream_only':True,
        'retry_bound_per_thread':64,
        'retry_g1t_site':'main+0x612120 -> main+0x61210c',
        'retry_g1s_site':'main+0x6e7bb0 -> main+0x6e7b94',
        'resource_stage_trace':True,'fdata_io_proof':True,
        'branch_trace_sites':18,
        'game_shaders_recompiled':False,
        'guest_modules_rewritten':False,
        'device_boot_verified':False,
        'not_a_gameplay_fix':True,
        'reason':'Test the original async mode4 stream availability, no synthetic assets'
    })
    (out/'mode4-retry-report.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-ipa',required=True,type=Path)
    ap.add_argument('--source-report',required=True,type=Path)
    ap.add_argument('--repo',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args()
    make(a.source_ipa,a.source_report,a.repo.resolve(),a.output)
