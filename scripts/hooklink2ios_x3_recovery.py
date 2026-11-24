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
    "        int hl_archive_write_ok = 1;\n#if TARGET_OS_IPHONE\n        if (g_arch_dir) {\n            // Only the engine's own default cache, never a user-selected archive.\n            NSString *default_dir = user ? [user.stringByDeletingLastPathComponent stringByAppendingPathComponent:@\"pso_archive\"] : nil;\n            if ((!e || !*e) && [g_arch_dir isEqualToString:default_dir]) hl_prune_archive(g_arch_dir);\n            uint64_t freeBytes = hl_archive_free(g_arch_dir);\n            hl_archive_write_ok = freeBytes >= (16ull << 30);\n            if (!hl_archive_write_ok)\n                MLOG(\"HookLink2iOS X3: pipeline archive read-only (free %.2f GiB; capture requires 16 GiB)\", freeBytes / 1073741824.0);\n        }\n#endif\n        ArchPlan *plan = arch_plan(g_arch_dir);"
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
  ],
  [
    "    NSError *first = nil;\n    id<MTLComputePipelineState> ps = cps_new_b(cs->fn, off, &first);",
    "    // This exact variant was recovered successfully on-device in the X3 Recovery log.\n    // Avoid provoking the compiler service a second time on each launch.\n    if (off && cs->rf.border && fn_off(cs->fn) && !strcmp(cs->key, \"278f48371bcf0d58_b\")) {\n        id<MTLComputePipelineState> known = cps_new_b(cs->fn, 0, out);\n        if (known) { MLOG(\"HookLink2iOS X3 smooth: known equivalent compute variant %s\", cs->key); return known; }\n    }\n    NSError *first = nil;\n    id<MTLComputePipelineState> ps = cps_new_b(cs->fn, off, &first);"
  ],
  [
    "static _Atomic int g_mem_hot; static _Atomic uint64_t g_mem_hot_n;",
    "static _Atomic int g_mem_hot; static _Atomic uint64_t g_mem_hot_n;\nstatic _Atomic int64_t hl_mem_room_mb = -1;"
  ],
  [
    "    int was = atomic_load(&g_mem_hot), hot = mem_hot_next(was, fp, room, cfg);",
    "    atomic_store_explicit(&hl_mem_room_mb, room, memory_order_relaxed);\n    int was = atomic_load(&g_mem_hot), hot = mem_hot_next(was, fp, room, cfg);"
  ],
  [
    "    if (!g_rh_n) return;\n    int hot = mem_hot();\n    uint64_t now = clock_gettime_nsec_np(CLOCK_MONOTONIC); void *drop[64]; unsigned nd = 0;",
    "    int hot = mem_hot();\n    // Only already-retired heaps enter this list; keep a tiny short-lived cache\n    // when there is measured headroom, not when iOS is near its limit.\n    int64_t room = atomic_load_explicit(&hl_mem_room_mb, memory_order_relaxed);\n    uint64_t cap = hot ? (room >= 1536 ? (32ull << 20) : 0) : RH_CAP;\n    uint64_t idle = hot ? 350000000ull : RH_IDLE_NS;\n    uint64_t now = clock_gettime_nsec_np(CLOCK_MONOTONIC); void *drop[64]; unsigned nd = 0;"
  ],
  [
    "        if (!hot && now - g_rh[old].t < RH_IDLE_NS && g_rh_bytes <= RH_CAP) break;   // under memory pressure every waiting heap goes (mem_hot)",
    "        if (cap && now - g_rh[old].t < idle && g_rh_bytes <= cap) break;"
  ],
  [
    "enum { PREREAD_SLOTS = 4096 }; static const uint64_t PREREAD_AGAIN_NS = 2000000000ull;",
    "enum { PREREAD_SLOTS = 16384 }; static const uint64_t PREREAD_AGAIN_NS = 2000000000ull;\nstatic _Atomic uint64_t hl_preread_pending, hl_preread_throttled;\nstatic int hl_preread_reserve(uint64_t bytes) {\n    // The serial utility queue must not accumulate gigabytes of stale advice\n    // during world loading. Small requests share a bounded 128 MiB window.\n    const uint64_t cap = 128ull << 20;\n    uint64_t n = atomic_load_explicit(&hl_preread_pending, memory_order_relaxed);\n    do { if (n > cap || bytes > cap - n) return 0; }\n    while (!atomic_compare_exchange_weak_explicit(&hl_preread_pending, &n, n + bytes,\n                                                  memory_order_relaxed, memory_order_relaxed));\n    return 1;\n}"
  ],
  [
    "    uint64_t now = clock_gettime_nsec_np(CLOCK_UPTIME_RAW); unsigned k = (unsigned)((a >> 12) * 0x9E3779B1u) % PREREAD_SLOTS;",
    "    uint64_t now = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);\n    // Hash actual host pages (16 KiB on iPhone), not assumed 4 KiB pages.\n    uint64_t h = a / pg; h ^= h >> 17; h *= 0x9E3779B97F4A7C15ull; h ^= h >> 32;\n    unsigned k = (unsigned)(h % PREREAD_SLOTS);"
  ],
  [
    "    atomic_store_explicit(&g_preread_seen[k].a, a, memory_order_relaxed);",
    "    if (!hl_preread_reserve(b - a)) { atomic_fetch_add_explicit(&hl_preread_throttled, 1, memory_order_relaxed); return; }\n    atomic_store_explicit(&g_preread_seen[k].a, a, memory_order_relaxed);"
  ],
  [
    "        atomic_fetch_add(&g_preread_ns, clock_gettime_nsec_np(CLOCK_UPTIME_RAW) - t0);",
    "        atomic_fetch_add(&g_preread_ns, clock_gettime_nsec_np(CLOCK_UPTIME_RAW) - t0);\n        atomic_fetch_sub_explicit(&hl_preread_pending, b - a, memory_order_relaxed);"
  ],
  [
    "    if (g_preread <= 0) return;\n    MLOG(\"[preread] up to frame",
    "    if (g_preread <= 0) return;\n    MLOG(\"HookLink2iOS X3 smooth: preread pending %.1f MiB, throttled %llu ranges\",\n         atomic_load(&hl_preread_pending) / 1048576.0, (unsigned long long)atomic_load(&hl_preread_throttled));\n    MLOG(\"[preread] up to frame"
  ],
  [
    "    __strong id<MTLBuffer> b = nil; size_t off = arena_alloc(OCC_BYTES, &b); if (!b) return 0;\n    g_occ_buf = b;",
    "    // Flush anything that could finish a segment before publishing a new job buffer.\n    rp_end(); ubd_land(); if (g_blit) { enc_b_end(g_blit); g_blit = nil; }\n    __strong id<MTLBuffer> b = nil; size_t off = arena_alloc(OCC_BYTES, &b); if (!b || !b.contents || !b.gpuAddress) return 0;\n    if (off > b.length || OCC_BYTES > b.length - off) return 0;\n    g_occ_buf = b;"
  ],
  [
    "    rp_end(); ubd_land(); if (g_blit) { enc_b_end(g_blit); g_blit = nil; }\n    id<MTL4ComputeCommandEncoder> ce = enc_c_begin(NULL); enc_c_pso(ce, g_occ_pso);",
    "    id<MTL4ComputeCommandEncoder> ce = enc_c_begin(NULL); enc_c_pso(ce, g_occ_pso);"
  ],
  [
    "            slots[(*n)++] = rep->occ_gpu[i]; }",
    "            id<MTLBuffer> vb = g_vis_ring[k].buf;\n            uint64_t addr = rep->occ_gpu[i], base = vb.gpuAddress;\n            if (!vb || !base || addr < base || addr - base > vb.length || vb.length - (addr - base) < 8 || ((addr - base) & 7)) return 0;\n            slots[(*n)++] = addr; }"
  ],
  [
    "    if (g_occ_job < 0 || g_occ_sub != g_fence || !g_occ_cpu || n > 32) return 0;",
    "    if (g_occ_job < 0 || g_occ_sub != g_fence || !g_occ_cpu || n > 32 || field > n || n - field < sizeof(uint32_t) || (field & 3)) return 0;"
  ],
  [
    "    uint32_t *hdr = (uint32_t *)(void *)g_occ_cpu; if (hdr[0] >= OCC_PATCH) { g_occ_fallback_n++; return 0; }",
    "    uint32_t *hdr = (uint32_t *)(void *)g_occ_cpu; if (hdr[0] >= OCC_PATCH || (uint32_t)g_occ_job >= hdr[1]) { g_occ_fallback_n++; return 0; }"
  ],
  [
    "static void pso4_init(void) {\n    static dispatch_once_t once;",
    "#if TARGET_OS_IPHONE\nstatic uint64_t hl_archive_free(NSString *dir) {\n    NSDictionary *v = [NSFileManager.defaultManager attributesOfFileSystemForPath:dir.stringByDeletingLastPathComponent error:nil];\n    return [v[NSFileSystemFreeSize] unsignedLongLongValue];\n}\nstatic int hl_cache_regular(NSString *p) {\n    struct stat st; return !lstat(p.fileSystemRepresentation, &st) && S_ISREG(st.st_mode);\n}\n// Before Metal maps any archives: reclaim only generated cache files, not\n// the manifest, save, RomFS, app bundle, or any custom DM_PSO_ARCHIVE.\nstatic void hl_prune_archive(NSString *dir) {\n    static int lock_fd = -1;\n    NSFileManager *fm = NSFileManager.defaultManager;\n    struct stat ds; if (lstat(dir.fileSystemRepresentation, &ds) || !S_ISDIR(ds.st_mode)) return;\n    NSString *lp = [dir stringByAppendingPathComponent:@\".hooklink-cache.lock\"];\n    int fd = open(lp.fileSystemRepresentation, O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);\n    if (fd < 0) return;\n    if (flock(fd, LOCK_EX | LOCK_NB)) { if (flock(fd, LOCK_SH | LOCK_NB)) { close(fd); return; } lock_fd = fd; return; }\n    lock_fd = fd;\n    const uint64_t reserve = 14ull << 30;\n    uint64_t before = hl_archive_free(dir);\n    if (before && before < reserve) {\n        NSRegularExpression *rx = [NSRegularExpression regularExpressionWithPattern:@\"^(p[0-9]+|[0-9]+-[0-9]+)\\\\.mtl4a$\" options:0 error:nil];\n        NSArray<NSString *> *names = [[fm contentsOfDirectoryAtPath:dir error:nil] sortedArrayUsingComparator:^NSComparisonResult(NSString *a, NSString *b) {\n            // Old prebuild-only bases first (full pair prebuild is off), then oldest runtime files.\n            BOOL ap = [a hasPrefix:@\"p\"], bp = [b hasPrefix:@\"p\"];\n            if (ap != bp) return ap ? NSOrderedAscending : NSOrderedDescending;\n            return [a compare:b options:NSNumericSearch];\n        }];\n        unsigned removed = 0, prebuild = 0;\n        for (NSString *n in names) {\n            if (hl_archive_free(dir) >= reserve) break;\n            if (![rx numberOfMatchesInString:n options:0 range:NSMakeRange(0,n.length)]) continue;\n            NSString *path = [dir stringByAppendingPathComponent:n];\n            if (!hl_cache_regular(path) || unlink(path.fileSystemRepresentation)) continue;\n            NSString *keys = arch_keys_path(path); if (hl_cache_regular(keys)) unlink(keys.fileSystemRepresentation);\n            removed++; prebuild += [n hasPrefix:@\"p\"];\n        }\n        if (prebuild) { NSString *stamp = [dir stringByAppendingPathComponent:@\"prebuilt.tsv\"]; if (hl_cache_regular(stamp)) unlink(stamp.fileSystemRepresentation); }\n        MLOG(\"HookLink2iOS X3 storage: pruned %u rebuildable archive files (%u prebuild), free %.2f -> %.2f GiB; target 14 GiB\", removed, prebuild, before / 1073741824.0, hl_archive_free(dir) / 1073741824.0);\n    }\n    // Hold the shared lock for the rest of this process; no patched second\n    // process can prune a cache in use. The fd closes on exit.\n    if (flock(lock_fd, LOCK_SH)) { close(lock_fd); lock_fd = -1; }\n}\n#endif\nstatic void pso4_init(void) {\n    static dispatch_once_t once;"
  ],
  [
    "    [NSFileManager.defaultManager createDirectoryAtPath:g_arch_dir withIntermediateDirectories:YES attributes:nil error:nil];\n    uint64_t t0 = bp_now(); NSError *e = nil;\n    NSString *path =",
    "#if TARGET_OS_IPHONE\n    if (!g_pre_out && hl_archive_free(g_arch_dir) < (16ull << 30)) {\n        atomic_store(&g_arch_cap_off, 1);\n        if (ep->compacting) g_compact_bad = 1;\n        atomic_fetch_sub(&g_arch_new, n); atomic_fetch_sub(&g_arch_new_vd, vd);\n        ser_end();\n        MLOG(\"HookLink2iOS X3 storage: archive write deferred; preserving guest disk reserve\");\n        return;\n    }\n#endif\n    [NSFileManager.defaultManager createDirectoryAtPath:g_arch_dir withIntermediateDirectories:YES attributes:nil error:nil];\n    uint64_t t0 = bp_now(); NSError *e = nil;\n    NSString *path ="
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
    return ["low-storage PSO capture admission and compaction guard", "equivalent compute variant fallback and verified shader fast path", "per-variant exponential XPC retry cooldown", "bounded pressure-aware retired heap reuse", "host-page preread hashing and bounded outstanding advice", "experimental GPU occlusion buffer bounds and segment ordering guards", "startup pruning of generated PSO files and runtime archive write reserve"]
