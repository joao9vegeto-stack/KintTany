#!/usr/bin/env python3
"""Selective, pin-compatible port of NXNative PR #2919 for Kakarot.

The upstream PR assumes newer dirty-page and texture-cache APIs than the
NX2Apple v1.3.1-rc2 pin. This port adapts the required mechanism to that
runtime instead of transplanting unrelated upstream cache/lifecycle changes.
Only NVN host runtime files are edited; game shaders and the cached Metal image
are never rebuilt or modified.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
UPSTREAM_COMMIT = "23427a7befb6662fec04aa810e0713e5c8d1dd96"
TITLE_ID = "010051C0134F8000"

FILES = (
    "dm/gfx/nvn/hle_nvn.c",
    "dm/gfx/nvn/nvn_dirty.c",
    "dm/gfx/nvn/nvn_dirty.h",
    "dm/gfx/nvn/nvn_mtl.m",
    "dm/gfx/nvn/nvn_obj.h",
)

def fail(message: str) -> "NoReturn":
    raise SystemExit("[KaKaRoTiOS] GPU-copy texture-order backport refused: " + message)

def replace_once(source: str, old: str, new: str, label: str) -> tuple[str, bool]:
    old_n, new_n = source.count(old), source.count(new)
    if old_n == 1 and new_n == 0:
        return source.replace(old, new, 1), True
    if old_n == 0 and new_n == 1:
        return source, False
    fail(f"{label}: expected one original anchor or one already-patched anchor; old={old_n}, new={new_n}.")
    raise AssertionError("unreachable")

def replace_in_function(source: str, signature: str, old: str, new: str, label: str) -> tuple[str, bool]:
    start = source.find(signature)
    if start < 0:
        fail(f"{label}: function not found: {signature}")
    end = source.find("\n}\n", start)
    if end < 0:
        fail(f"{label}: function boundary not found.")
    body = source[start:end + 3]
    updated, changed = replace_once(body, old, new, label)
    return source[:start] + updated + source[end + 3:], changed

OWN_TRACKING = """static _Atomic(pthread_t) g_nvn_dirty_own_thread;
static _Atomic uint64_t g_nvn_dirty_own_writes;
static void own_note(void) {
    pthread_t own = atomic_load(&g_nvn_dirty_own_thread);
    if (own && pthread_equal(own, pthread_self()))
        atomic_fetch_add(&g_nvn_dirty_own_writes, 1);
}
void nvn_dirty_own_thread(void) {
    atomic_store(&g_nvn_dirty_own_thread, pthread_self());
}
uint64_t nvn_dirty_own_writes(void) {
    return atomic_load(&g_nvn_dirty_own_writes);
}
"""

GPU_WRITTEN = """// GPU buffer copies do not trigger the CPU page-fault path. Publish their
// destinations into the same dirty generations while retaining read-only
// protection for a later CPU writer.
void nvn_dirty_gpu_written(uintptr_t addr, size_t len) {
    if (!len || len > UINTPTR_MAX - addr) return;
    uintptr_t end = addr + len;
    pthread_mutex_lock(&g_slot_mu);
    for (int i = 0, n = atomic_load(&g_nr); i < n; i++) {
        range_t *r = rg(i);
        if (!live_at(i)) continue;
        uintptr_t base = r->base, limit = r->end;
        uintptr_t lo = addr > base ? addr : base;
        uintptr_t hi = end < limit ? end : limit;
        if (hi <= lo) continue;
        uintptr_t first = (lo - base) >> g_shift;
        uintptr_t last = (hi - 1 - base) >> g_shift;
        for (uintptr_t p = first; p <= last; p++) {
            uint8_t state = PG_PROT;
            if (atomic_compare_exchange_strong(&r->state[p], &state, PG_BUSY)) {
                stamp_page(r, p);
                sparse_note(r, p);
                atomic_store(&r->state[p], PG_PROT);
            }
        }
    }
    pthread_mutex_unlock(&g_slot_mu);
    own_note();
}
"""

PREP_WRITE_OLD = """static void prep_write(void *addr, size_t len) {
    uintptr_t a = (uintptr_t)addr, e = a + len; int n = atomic_load(&g_nr);
    if (!len) return;
    for (int i = 0; i < n; i++) {
        range_t *r = rg(i);
        if (!live_at(i) || e <= r->base || a >= r->end) continue;
        uintptr_t lo = a > r->base ? a : r->base, hi = e < r->end ? e : r->end;
        release_pages(r, (lo - r->base) >> g_shift, (hi - 1 - r->base) >> g_shift, &g_preps);
    }
}
"""
PREP_WRITE_NEW = """static void prep_write(void *addr, size_t len) {
    uintptr_t a = (uintptr_t)addr, e = a + len; int n = atomic_load(&g_nr), touched = 0;
    if (!len) return;
    for (int i = 0; i < n; i++) {
        range_t *r = rg(i);
        if (!live_at(i) || e <= r->base || a >= r->end) continue;
        uintptr_t lo = a > r->base ? a : r->base, hi = e < r->end ? e : r->end;
        touched = 1;
        release_pages(r, (lo - r->base) >> g_shift, (hi - 1 - r->base) >> g_shift, &g_preps);
    }
    if (touched) own_note();
}
"""

VPT_WALK_OLD = """static int vpt_walk(const void *pool, uint64_t a, uint64_t n, uint64_t gen, int (*fn)(const uint8_t *, uint64_t, uint64_t), uint64_t arg) {
    pthread_mutex_lock(&g_vp_mu); struct vpool *v = vpool_at(pool, a); int r = 0;
    if (!v) { pthread_mutex_unlock(&g_vp_mu); return 1; }
    const uint8_t *rs = NULL, *re = NULL; uint64_t o = a - (uint64_t)(uintptr_t)v->base;
    for (uint64_t at = o & ~0xFFFull; at < o + n && at < v->size && !r; at += 0x1000) {
        const vpte *e = vpt_get(v, at);
        if (!e) { at |= (2u << 20) - 1; at -= 0xFFF; continue; }   // a leaf never mapped: skip its 2 MB
        if (gen != ~0ull && e->gen > gen) { r = 1; break; }
        if (!e->phys) continue;
        if (rs && e->phys == re) { re += 0x1000; continue; }
        if (rs) r = fn(rs, (uint64_t)(re - rs), arg);
        rs = e->phys; re = rs + 0x1000;
    }
    if (!r && rs) r = fn(rs, (uint64_t)(re - rs), arg);
    pthread_mutex_unlock(&g_vp_mu); return r;
}
"""
VPT_WALK_NEW = """static int vpt_walk_locked(const struct vpool *v, uint64_t a, uint64_t n, uint64_t gen,
                           int (*fn)(const uint8_t *, uint64_t, uint64_t), uint64_t arg) {
    int r = 0;
    const uint8_t *rs = NULL, *re = NULL;
    uint64_t o = a - (uint64_t)(uintptr_t)v->base;
    for (uint64_t at = o & ~0xFFFull; at < o + n && at < v->size && !r; at += 0x1000) {
        const vpte *e = vpt_get(v, at);
        if (!e) { at |= (2u << 20) - 1; at -= 0xFFF; continue; }
        if (gen != ~0ull && e->gen > gen) { r = 1; break; }
        if (!e->phys) continue;
        if (rs && e->phys == re) { re += 0x1000; continue; }
        if (rs) r = fn(rs, (uint64_t)(re - rs), arg);
        rs = e->phys; re = rs + 0x1000;
    }
    if (!r && rs) r = fn(rs, (uint64_t)(re - rs), arg);
    return r;
}
static int vpt_walk(const void *pool, uint64_t a, uint64_t n, uint64_t gen,
                    int (*fn)(const uint8_t *, uint64_t, uint64_t), uint64_t arg) {
    pthread_mutex_lock(&g_vp_mu);
    struct vpool *v = vpool_at(pool, a);
    int r = v ? vpt_walk_locked(v, a, n, gen, fn, arg) : 1;
    pthread_mutex_unlock(&g_vp_mu);
    return r;
}
static int run_buffer_range(const uint8_t *p, uint64_t n, uint64_t arg) {
    nvn_buffer_range_fn note = *(nvn_buffer_range_fn *)(uintptr_t)arg;
    note((uint64_t)(uintptr_t)p, n);
    return 0;
}
// Resolve sparse virtual destinations to their physical backing now, while
// the mapping is still held. An unmap may otherwise erase the attribution
// before the GPU copy completes.
void nvn_buffer_write_ranges(uint64_t a, uint64_t n, nvn_buffer_range_fn note) {
    if (!n) return;
    int sparse = 0;
    pthread_mutex_lock(&g_vp_mu);
    for (int i = 0; i < g_nvp; i++) {
        const struct vpool *v = g_vp[i];
        uint64_t base = (uint64_t)(uintptr_t)v->base;
        if (a >= base && a - base < v->size) {
            sparse = 1;
            vpt_walk_locked(v, a, n, ~0ull, run_buffer_range, (uint64_t)(uintptr_t)&note);
            break;
        }
    }
    pthread_mutex_unlock(&g_vp_mu);
    if (!sparse) note(a, n);
}
"""

def patch_dirty(source: str) -> tuple[str, bool]:
    changed = False
    own_marker = "static _Atomic(pthread_t) g_nvn_dirty_own_thread;"
    if own_marker not in source:
        anchor = "static _Atomic uint64_t g_sparse_writes;"
        source, did = replace_once(source, anchor, OWN_TRACKING + anchor, "insert replay-thread write tracking")
        changed |= did
    required_own = ("static void own_note(void)", "void nvn_dirty_own_thread(void)", "uint64_t nvn_dirty_own_writes(void)")
    if any(x not in source for x in required_own):
        fail("dirty tracker has a partial replay-thread write-tracking insertion.")

    source, did = replace_once(
        source,
        "    stamp_page(r, p); sparse_note(r, p);\n    atomic_store(&r->state[p], PG_NONE);",
        "    stamp_page(r, p); sparse_note(r, p); own_note();\n    atomic_store(&r->state[p], PG_NONE);",
        "count CPU page-fault writes made by the replay thread",
    )
    changed |= did

    source, did = replace_once(source, PREP_WRITE_OLD, PREP_WRITE_NEW, "count replay-thread host writes")
    changed |= did

    if "void nvn_dirty_gpu_written(uintptr_t addr, size_t len)" not in source:
        anchor = "uint64_t nvn_dirty_now(void) { return atomic_load(&g_now); }\n"
        source, did = replace_once(source, anchor, anchor + GPU_WRITTEN, "add GPU-write dirty-page publication")
        changed |= did
    elif "own_note();" not in source[source.index("void nvn_dirty_gpu_written("):source.index("void nvn_dirty_gpu_written(") + 1800]:
        fail("GPU dirty-page function is present but lacks replay-thread write publication.")

    if "void nvn_dirty_own_thread(void) {" not in source:
        fail("dirty tracker implementation is missing nvn_dirty_own_thread.")
    return source, changed

def patch_dirty_header(source: str) -> tuple[str, bool]:
    if "nvn_dirty_gpu_written(uintptr_t addr, size_t len);" in source:
        if "nvn_dirty_own_writes(void);" in source and "nvn_dirty_own_thread(void);" in source:
            return source, False
        fail("dirty header has a partial GPU-write API insertion.")
    anchor = "uint64_t nvn_dirty_sparse_writes(void);                            // Writes so far to pages protected that way\n"
    new = (
        anchor
        + "void nvn_dirty_own_thread(void);                                   // Calling thread replays GPU commands\n"
        + "uint64_t nvn_dirty_own_writes(void);                               // CPU/GPU writes ordered on the replay thread\n"
        + "void nvn_dirty_gpu_written(uintptr_t addr, size_t len);             // GPU copies bypass CPU page faults\n"
    )
    return replace_once(source, anchor, new, "declare GPU and replay-thread dirty tracking")

def patch_hle(source: str) -> tuple[str, bool]:
    if "void nvn_buffer_write_ranges(" in source:
        if "static int vpt_walk_locked(" in source and "nvn_buffer_range_fn note" in source:
            return source, False
        fail("sparse buffer-range helper is only partially present.")
    return replace_once(source, VPT_WALK_OLD, VPT_WALK_NEW, "capture sparse physical copy destinations")

def patch_obj(source: str) -> tuple[str, bool]:
    if "typedef void (*nvn_buffer_range_fn)(uint64_t addr, uint64_t size);" in source:
        if "void nvn_buffer_write_ranges(uint64_t addr, uint64_t size, nvn_buffer_range_fn note);" in source:
            return source, False
        fail("NVN buffer-range callback type is only partially declared.")
    anchor = "uint64_t nvn_new_serial(void);\n"
    new = (
        "typedef void (*nvn_buffer_range_fn)(uint64_t addr, uint64_t size);\n"
        "void nvn_buffer_write_ranges(uint64_t addr, uint64_t size, nvn_buffer_range_fn note);\n"
        + anchor
    )
    return replace_once(source, anchor, new, "declare sparse physical buffer-copy callback")

POST_HELPERS = """static void post(post_op o);
enum { POST_BUFFER_COPY = 5, B2B_MAX = 4096 };
static uint64_t g_b2b_lo[B2B_MAX], g_b2b_hi[B2B_MAX];
static int g_b2b_n, g_b2b_over;
static uint64_t g_b2b_cuts, g_b2b_nocut, g_b2b_runs, g_b2b_bytes;

static void post_buffer_copy(uint64_t dst, uint64_t n) {
    if (!n || n > UINT64_MAX - dst) return;
    uint64_t end = dst + n;
    if (g_npost) {
        post_op *last = &g_post[g_npost - 1];
        if (last->kind == POST_BUFFER_COPY && dst <= last->copy_end && last->addr <= end) {
            if (dst < last->addr) last->addr = dst;
            if (end > last->copy_end) last->copy_end = end;
            return;
        }
    }
    post((post_op){.kind = POST_BUFFER_COPY, .addr = dst, .copy_end = end});
}
static int copy_cut_on(void) {
    static int value = -1;
    if (value < 0) {
        const char *e = getenv("DM_NVN_COPY_CUT");
        value = !(e && !strcmp(e, "0"));
        if (!value) MLOG("DM_NVN_COPY_CUT=0: buffer-copy runs are not cut before later commands");
    }
    return value;
}
static void b2b_note(uint64_t dst, uint64_t n) {
    if (!n || !copy_cut_on() || n > UINT64_MAX - dst) return;
    uint64_t end = dst + n;
    if (g_b2b_n && dst <= g_b2b_hi[g_b2b_n - 1] && g_b2b_lo[g_b2b_n - 1] <= end) {
        if (dst < g_b2b_lo[g_b2b_n - 1]) g_b2b_lo[g_b2b_n - 1] = dst;
        if (end > g_b2b_hi[g_b2b_n - 1]) g_b2b_hi[g_b2b_n - 1] = end;
        return;
    }
    if (g_b2b_n == B2B_MAX) {
        g_b2b_over = 1;
        if (dst < g_b2b_lo[B2B_MAX - 1]) g_b2b_lo[B2B_MAX - 1] = dst;
        if (end > g_b2b_hi[B2B_MAX - 1]) g_b2b_hi[B2B_MAX - 1] = end;
        return;
    }
    g_b2b_lo[g_b2b_n] = dst;
    g_b2b_hi[g_b2b_n++] = end;
}
static void buffer_copy_note(uint64_t dst, uint64_t n) {
    post_buffer_copy(dst, n);
    b2b_note(dst, n);
}
"""

GPU_READ_WAIT = """static id<MTLSharedEvent> g_tex_read_ev;
static uint64_t g_tex_read_v;
static int gpu_read_wait(int site) {
    rp_end();
    ubd_land();
    if (g_blit) { enc_b_end(g_blit); g_blit = nil; }
    up_flush();
    res_commit();
    [g_cb endCommandBuffer];
    rec_commit(g_cb, nil);
    if (!g_tex_read_ev) g_tex_read_ev = [g_dev newSharedEvent];
    rec_signal(g_tex_read_ev, ++g_tex_read_v);
    rec_drain();
    uint64_t w0 = ws_t0();
    int ok = [g_tex_read_ev waitUntilSignaledValue:g_tex_read_v timeoutMS:10000];
    if (ws_on()) ws_put(site, w0, 1);
    if (ok) drw_drained();
    g_cb = rec_cb_new();
    [g_cb beginCommandBufferWithAllocator:g_alloc4[g_alloc_cur]];
    return ok;
}
"""

TEX_CPU_WAIT = """static int gpu_read_wait(int site);
static int tex_cpu_wait(const tex_t *t) {
    uint64_t lo = (uint64_t)(uintptr_t)t->mem, hi = lo + t->L.size;
    int pending = drw_valid() ? drw_hits(lo, t->L.size) || (nvn_sparse_gen() && g_ndrw) :
        pend_hits(lo, t->L.size) || g_sbw_over || sbw_hits(lo, hi) || gw_live(lo, hi) ||
        (nvn_sparse_gen() && (g_npend || g_nsbw || g_nsbw_w || g_fence > g_done));
    if (g_cb && pending) {
        if (!gpu_read_wait(WS_UPALLOC))
            MDIE("CPU texture upload: the GPU did not finish its storage writes within 10 s");
        return 1;
    }
    if (!g_cb && (gw_live(lo, hi) || nvn_sparse_gen())) {
        mtl_finish_gpu_at(WS_UPALLOC);
        return 1;
    }
    return 0;
}
"""

B2B_FLUSH = """static void b2b_flush(int cut) {
    if (!g_b2b_n) return;
    if (cut) {
        uint64_t generation = g_cbgen;
        if (!g_enc) {
            if (g_blit) { enc_b_end(g_blit); g_blit = nil; }
            g_cut_copy = 1;
            sub_cut();
        }
        if (g_cbgen != generation) g_b2b_cuts++;
        else g_b2b_nocut++;
    }
    for (int i = 0; i < g_b2b_n; i++) {
        uint64_t len = g_b2b_hi[i] - g_b2b_lo[i];
        nvn_dirty_gpu_written((uintptr_t)g_b2b_lo[i], (size_t)len);
        g_b2b_bytes += len;
    }
    if (++g_b2b_runs <= 3 || g_b2b_runs % 500 == 0)
        MLOG("buffer copy runs %llu: committed before next command %llu, not committable %llu, %.1f MB stamped%s",
             (unsigned long long)g_b2b_runs, (unsigned long long)g_b2b_cuts,
             (unsigned long long)g_b2b_nocut, g_b2b_bytes / 1048576.0,
             g_b2b_over ? ", range list overflowed and was conservatively merged" : "");
    g_b2b_n = 0;
    g_b2b_over = 0;
}
"""

def patch_mtl(source: str) -> tuple[str, bool]:
    changed = False
    source, did = replace_once(
        source,
        "typedef struct { int kind; volatile uint32_t *val; uint32_t mode, v; uint64_t addr; uint32_t type; void *vis; uint32_t seg; } post_op;",
        "typedef struct { int kind; volatile uint32_t *val; uint32_t mode, v; uint64_t addr; uint32_t type; void *vis; uint32_t seg; uint64_t copy_end; } post_op;",
        "extend deferred operations for buffer-copy destinations",
    )
    changed |= did

    if "static void buffer_copy_note(uint64_t dst, uint64_t n)" not in source:
        anchor = "static post_op *g_post; static int g_npost, g_postcap;\n"
        source, did = replace_once(source, anchor, anchor + POST_HELPERS, "add buffer-copy run tracking")
        changed |= did
    elif "static void post_buffer_copy(uint64_t dst, uint64_t n)" not in source or "static void b2b_note(" not in source:
        fail("buffer-copy helper block is partial.")

    source, did = replace_once(
        source,
        "g_sub_thread = pthread_self(); atomic_store(&g_sub_thread_set, 1);",
        "nvn_dirty_own_thread();\n    g_sub_thread = pthread_self(); atomic_store(&g_sub_thread_set, 1);",
        "mark the replay thread for ordered write tracking",
    )
    changed |= did

    source, did = replace_once(
        source,
        "g_npost = 0; g_vis = nil; g_vis_n = 0; g_vis_cur = -1; pend_reset();",
        "g_npost = 0; g_vis = nil; g_vis_n = 0; g_vis_cur = -1; pend_reset();\n    g_b2b_n = 0; g_b2b_over = 0;",
        "reset the current buffer-copy run at submission start",
    )
    changed |= did

    source, did = replace_in_function(
        source,
        "void mtl_sub_copy(uint64_t src, uint64_t dst, uint64_t n) {",
        "    enc_b_copy_buffer(blit_buf(src, src + n, dst, dst + n),",
        "    if (src != dst && n) nvn_buffer_write_ranges(dst, n, buffer_copy_note);\n"
        "    enc_b_copy_buffer(blit_buf(src, src + n, dst, dst + n),",
        "capture physical buffer-copy destination ranges",
    )
    changed |= did

    source, did = replace_once(
        source,
        "if (ops[i].kind == 1) continue;   // A terminal release publishes after every earlier GPU write has landed.",
        "if (ops[i].kind == 1) continue;   // A terminal release publishes after every earlier GPU write has landed.\n"
        "        else if (ops[i].kind == POST_BUFFER_COPY) nvn_dirty_gpu_written((uintptr_t)ops[i].addr, (size_t)(ops[i].copy_end - ops[i].addr));",
        "publish completed GPU buffer-copy writes",
    )
    changed |= did

    old_stats = "if (ws_on()) for (int i = 0; i < n; i++) { int k = g_post[i].kind == 2 ?"
    new_stats = "if (ws_on()) for (int i = 0; i < n; i++) { if (g_post[i].kind == POST_BUFFER_COPY) continue; int k = g_post[i].kind == 2 ?"
    source, did = replace_once(source, old_stats, new_stats, "exclude internal copy records from counter statistics")
    changed |= did

    # A CPU snapshot must wait for outstanding GPU writes; GPU-side uploads remain asynchronous.
    if "static int tex_cpu_wait(const tex_t *t)" not in source:
        anchor = "static id<MTLTexture> pkg_upload_(const tex_t *t, uint64_t *stamp, id<MTLTexture> reuse, MTLTextureUsage keep) {"
        source, did = replace_once(source, anchor, TEX_CPU_WAIT + anchor, "add CPU texture-upload storage hazard check")
        changed |= did
    elif "static int gpu_read_wait(int site);" not in source:
        fail("CPU texture wait helper lacks its GPU read-wait declaration.")

    source, did = replace_in_function(
        source,
        "static id<MTLTexture> pkg_upload_(const tex_t *t, uint64_t *stamp, id<MTLTexture> reuse, MTLTextureUsage keep) {",
        "    const uint8_t *src = t->mem; uint8_t *part = NULL;",
        "    if (tex_cpu_wait(t) && stamp) {\n"
        "        *stamp = nvn_dirty_now();\n"
        "        if (sparse) nvn_sparse_protect(t->pool, (uint64_t)(uintptr_t)t->mem, t->L.size);\n"
        "        else nvn_dirty_protect(t->mem, t->L.size);\n"
        "    }\n"
        "    const uint8_t *src = t->mem; uint8_t *part = NULL;",
        "wait before CPU reads texture storage",
    )
    changed |= did

    source, did = replace_once(
        source,
        "uint64_t wseen, wframe;            // nvn_dirty_sparse_writes and the frame at the last look for rewritten tiles",
        "uint64_t wseen, wframe, wown;      // sparse write count, frame and replay-thread write count at the last sync",
        "track replay-thread writes for sparse placement textures",
    )
    changed |= did

    source, did = replace_once(
        source,
        "static void sparse_sync(NvSparse *s, const tex_t *t, int whole) {\n"
        "    id<MTLTexture> stex = s->tex; if (!stex) return;\n",
        "static void sparse_sync(NvSparse *s, const tex_t *t, int whole) {\n"
        "    id<MTLTexture> stex = s->tex; if (!stex) return;\n"
        "    if (!s->gpu) tex_cpu_wait(t);\n"
        "    if (whole) s->wown = nvn_dirty_own_writes();\n",
        "wait before sparse CPU tile snapshots and set their write baseline",
    )
    changed |= did

    source, did = replace_once(
        source,
        "if (!s->gpu && nvn_dirty_sparse_writes() != s->wseen && atomic_load(&g_cur_frame) - s->wframe >= 60) sparse_sync(s, t, 2);",
        "if (!s->gpu && nvn_dirty_sparse_writes() != s->wseen &&\n"
        "        (s->wown != nvn_dirty_own_writes() || atomic_load(&g_cur_frame) - s->wframe >= 60)) sparse_sync(s, t, 2);",
        "refresh sparse textures immediately after replay-ordered GPU writes",
    )
    changed |= did

    if "static int gpu_read_wait(int site) {" not in source:
        anchor = "static void mdi_wait(void) {\n"
        source, did = replace_once(source, anchor, GPU_READ_WAIT + anchor, "add shared GPU-read completion wait")
        changed |= did

    if "static void b2b_flush(int cut) {" not in source:
        anchor = "void mtl_exec(const uint8_t *p) {\n"
        source, did = replace_once(source, anchor, B2B_FLUSH + anchor, "add buffer-copy run completion")
        changed |= did

    source, did = replace_in_function(
        source,
        "void mtl_exec(const uint8_t *p) {",
        "        switch (h.op) {",
        "        if (g_b2b_n && h.op != OP_COPY_B2B && !(h.op == OP_END && g_ret_n))\n"
        "            b2b_flush(h.op != OP_END || g_nrest);\n"
        "        switch (h.op) {",
        "flush buffer-copy runs before subsequent commands can upload their storage",
    )
    changed |= did

    required = (
        "POST_BUFFER_COPY = 5",
        "nvn_buffer_write_ranges(dst, n, buffer_copy_note)",
        "nvn_dirty_gpu_written((uintptr_t)ops[i].addr",
        "static int tex_cpu_wait(const tex_t *t)",
        "if (!s->gpu) tex_cpu_wait(t);",
        "s->wown != nvn_dirty_own_writes()",
        "static int gpu_read_wait(int site) {",
        "static void b2b_flush(int cut) {",
        "b2b_flush(h.op != OP_END || g_nrest);",
    )
    missing = [x for x in required if x not in source]
    if missing:
        fail("post-patch NVN source markers missing: " + ", ".join(missing))
    return source, changed

def self_test() -> None:
    assert len(FILES) == 5 and len(set(FILES)) == 5
    assert "nvn_dirty_gpu_written" in GPU_WRITTEN
    assert "nvn_buffer_write_ranges" in VPT_WALK_NEW
    assert "POST_BUFFER_COPY = 5" in POST_HELPERS
    assert "g_b2b_nocut" in B2B_FLUSH
    assert "nvn_dirty_own_writes" in TEX_CPU_WAIT
    print("[KaKaRoTiOS] PR #2919 adaptation contract: GPU copy ordering, sparse physical attribution, CPU-upload waits, and dirty-page publication.")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.engine_root is None:
        parser.error("--engine-root is required unless --self-test is used")

    engine = args.engine_root.resolve()
    root = engine.parent
    pin_file = root / ".upstream-ref"
    pin = pin_file.read_text(encoding="utf-8").strip() if pin_file.is_file() else ""
    if pin != ENGINE_PIN:
        fail(f"NXNative upstream pin is {pin!r}; expected {ENGINE_PIN}.")
    sources = {}
    for rel in FILES:
        path = engine / rel
        if not path.is_file():
            fail(f"pinned NVNative source file is missing: {rel}")
        sources[rel] = path.read_text(encoding="utf-8")

    handlers = {
        "dm/gfx/nvn/hle_nvn.c": patch_hle,
        "dm/gfx/nvn/nvn_dirty.c": patch_dirty,
        "dm/gfx/nvn/nvn_dirty.h": patch_dirty_header,
        "dm/gfx/nvn/nvn_mtl.m": patch_mtl,
        "dm/gfx/nvn/nvn_obj.h": patch_obj,
    }
    output = {}
    changed = []
    for rel, handler in handlers.items():
        output[rel], did = handler(sources[rel])
        if did:
            changed.append(rel)

    if args.check_only:
        print("[KaKaRoTiOS] NVN GPU-copy ordering source anchors and postconditions verified; no files written.")
        return 0
    for rel, text in output.items():
        path = engine / rel
        tmp = path.with_suffix(path.suffix + ".kakarot-copy-tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    print("[KaKaRoTiOS] Applied selective NVN GPU-copy ordering adaptation of NXNative PR #2919 (" + UPSTREAM_COMMIT + ").")
    print("[KaKaRoTiOS] Modified: " + (", ".join(changed) if changed else "already applied; no source changes"))
    print("[KaKaRoTiOS] Buffer copies are attributed to physical sparse pages, committed before later uploads where possible, and published at GPU completion.")
    print("[KaKaRoTiOS] CPU snapshots wait for pending GPU storage writes; sparse placement tiles refresh on replay-thread writes.")
    print("[KaKaRoTiOS] No shader sources, shader tables, DMSH_CHAIN, cached Metal library, RomFS or AOC changed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
