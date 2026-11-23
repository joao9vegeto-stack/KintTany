#!/usr/bin/env python3
"""Runtime-only fixes for the exact HookLink X3 engine. No shader ABI changes."""
from pathlib import Path

REPLACEMENTS = [
  [
    "    uint64_t loop_sub, loop_gpu; _Atomic int loop_reported;",
    "    uint64_t hl_cps_retry_at[2]; uint8_t hl_cps_retry_count[2];  // bounded retry of a transient compiler failure, per variant\n    uint64_t loop_sub, loop_gpu; _Atomic int loop_reported;"
  ],
  [
    "        ArchPlan *plan = arch_plan(g_arch_dir);",
    "        int hl_archive_write_ok = 1;\n#if TARGET_OS_IPHONE\n        if (g_arch_dir) {\n            NSString *parent = [g_arch_dir stringByDeletingLastPathComponent];\n            NSDictionary *volume = [NSFileManager.defaultManager attributesOfFileSystemForPath:parent error:nil];\n            NSNumber *freeBytes = volume[NSFileSystemFreeSize];\n            const uint64_t reserve = 12ull << 30;\n            hl_archive_write_ok = freeBytes && freeBytes.unsignedLongLongValue >= reserve;\n            if (!hl_archive_write_ok)\n                MLOG(\"HookLink2iOS X3: pipeline archive read-only for this run (free %.2f GiB, 12 GiB reserve for guest files); existing indexed PSOs retained\", freeBytes.unsignedLongLongValue / 1073741824.0);\n        }\n#endif\n        ArchPlan *plan = arch_plan(g_arch_dir);"
  ],
  [
    "            arch_compact_pick(runf);",
    "            if (hl_archive_write_ok) arch_compact_pick(runf);"
  ],
  [
    "        else if (g_arch_dir) {\n            g_ep = ep_new();",
    "        else if (g_arch_dir && hl_archive_write_ok) {\n            g_ep = ep_new();"
  ],
  [
    "static id<MTLComputePipelineState> cps_new(id<MTLFunction> f, NSError **e) { return cps_new_b(f, 0, e); }",
    "// Retry an equivalent variant only when border corrections were disabled.\n// encode_args binds a zero correction mask when no sampler needs corrections.\nstatic id<MTLComputePipelineState> hl_x3_cps_recover(NvShader *cs, int off, NSError **out) {\n    NSError *first = nil;\n    id<MTLComputePipelineState> ps = cps_new_b(cs->fn, off, &first);\n    if (ps) return ps;\n    if (off && cs->rf.border && fn_off(cs->fn) && err_compiler_died(first)) {\n        NSError *alternate = nil;\n        ps = cps_new_b(cs->fn, 0, &alternate);\n        if (ps) {\n            MLOG(\"HookLink2iOS X3: compute %s recovered with original border-corrected variant\", cs->key);\n            return ps;\n        }\n        MLOG(\"HookLink2iOS X3: compute %s alternative variant also refused: %s\", cs->key,\n             alternate.localizedDescription.UTF8String ?: \"unknown\");\n    }\n    if (out) *out = first;\n    return nil;\n}\nstatic id<MTLComputePipelineState> cps_new(id<MTLFunction> f, NSError **e) { return cps_new_b(f, 0, e); }"
  ],
  [
    "NvShader *cs = warm_shader(t->key, 5); NSError *e = nil; id ps = cs ? cps_new_b(cs->fn, 1, &e) : nil;",
    "NvShader *cs = warm_shader(t->key, 5); NSError *e = nil; id ps = cs ? hl_x3_cps_recover(cs, 1, &e) : nil;"
  ],
  [
    "if (cs && !ps) MLOG(\"[RED] background compute pipeline creation failed: %s\", e.localizedDescription.UTF8String);",
    "if (cs && !ps) MLOG(\"[RED] background compute pipeline creation failed for %s: %s\", cs->key, e.localizedDescription.UTF8String);"
  ],
  [
    "        NSError *e = nil; uint64_t bt = bp_now(); ps = cps_new_b(cs->fn, off, &e);\n        g_bp_pso_n++; g_bp_pso_ns += bp_now() - bt;\n        if (!ps) {\n            int interrupted = err_compiler_died(e);\n            if (!interrupted) cs->cps_failed = 1;\n            MLOG(\"[RED] failed to create compute pipeline for %s: %s (%s)\", cs->key, e.localizedDescription.UTF8String,\n                 interrupted ? \"this dispatch is skipped, a later dispatch can retry\" : \"its dispatches are skipped\");\n            return nil;\n        }",
    "        if (bp_now() < cs->hl_cps_retry_at[off]) return nil;\n        NSError *e = nil; uint64_t bt = bp_now(); ps = hl_x3_cps_recover(cs, off, &e);\n        g_bp_pso_n++; g_bp_pso_ns += bp_now() - bt;\n        if (!ps) {\n            int interrupted = err_compiler_died(e);\n            if (!interrupted) cs->cps_failed = 1;\n            if (interrupted) {\n                unsigned n = cs->hl_cps_retry_count[off], shift = n > 4 ? 4 : n;\n                uint64_t delay = 500000000ull << shift;\n                cs->hl_cps_retry_at[off] = bp_now() + delay;\n                if (n < 5) cs->hl_cps_retry_count[off] = n + 1;\n                MLOG(\"[RED] compute %s: compiler XPC interrupted; retry after %.1f s (dispatch skipped until a real pipeline succeeds)\", cs->key, delay / 1e9);\n            } else MLOG(\"[RED] failed to create compute pipeline for %s: %s (its dispatches are skipped)\", cs->key, e.localizedDescription.UTF8String);\n            return nil;\n        }\n        cs->hl_cps_retry_at[off] = 0;\n        cs->hl_cps_retry_count[off] = 0;"
  ]
]

def apply(engine):
    engine = Path(engine)
    path = engine / "dm/gfx/nvn/nvn_mtl.m"
    header = engine / "dm/gfx/nvn/dmsh_chain.h"
    original_header = header.read_bytes()
    source = path.read_text(encoding="utf-8")
    for anchor, replacement in REPLACEMENTS:
        if source.count(anchor) != 1:
            raise RuntimeError("X3 patch anchor absent or duplicated: " + anchor[:120])
        source = source.replace(anchor, replacement, 1)
    path.write_text(source, encoding="utf-8")
    if header.read_bytes() != original_header:
        raise RuntimeError("Shader chain header unexpectedly changed")
    return ["low-storage PSO capture admission and compaction guard", "equivalent compute variant fallback", "per-variant exponential XPC retry cooldown", "identified compute shader in prewarm diagnostics"]
