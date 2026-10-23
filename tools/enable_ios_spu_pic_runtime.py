#!/usr/bin/env python3
"""Enable PS3Recomp's unlifted-SPU interpreter and position-independent lifts.

The pinned runtime already contains a complete SPU interpreter, but its
unlifted-code fallback is opt-in.  This patch adds the PIC function registry
used by the PC port and the runtime capture format consumed by
``m793_lift_spu_pic.py``.  It intentionally does not infer equivalence from a
fingerprint: PIC lifts match the captured instruction bytes before dispatch.
"""
from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "ASCENSION_M793_SPU_PIC_RUNTIME_V1"

PIC_MATCH = r'''/* ASCENSION_M793_SPU_PIC_RUNTIME_V1 */
#ifndef SPU_PIC_MATCH_H
#define SPU_PIC_MATCH_H
#include <stdint.h>
#include <string.h>
static inline int spu_pic_entry_matches(const uint8_t* ls, uint32_t ls_size,
                                        uint32_t pc, const uint8_t* code,
                                        uint32_t addr, uint32_t lo, uint32_t hi,
                                        const uint32_t* ranges, uint32_t nranges)
{
    if (pc < addr - lo) return 0;
    if (!nranges) {
        const uint32_t base = pc - (addr - lo), span = hi - lo;
        if (base > ls_size || span > ls_size - base) return 0;
        return memcmp(ls + base, code + lo, span) == 0;
    }
    for (uint32_t i = 0; i < nranges; ++i) {
        const uint32_t a = ranges[2 * i], b = ranges[2 * i + 1];
        if (a < lo || b > hi || b <= a || (a < addr && pc < addr - a)) return 0;
        const uint32_t at = pc + a - addr;
        if (at > ls_size || b - a > ls_size - at) return 0;
        if (memcmp(ls + at, code + a, b - a) != 0) return 0;
    }
    return 1;
}
#endif
'''

PIC_API = r'''/* ASCENSION_M793_SPU_PIC_RUNTIME_V1 */
#define SPU_PIC_MAX_ENTRIES 65536u
#define SPU_PIC_MAX_SPAN    0x8000u
typedef struct {
    uint64_t key;
    const spu_pic_entry* entry;
    const uint8_t* code;
} spu_pic_slot;
static spu_pic_slot s_pic[SPU_PIC_MAX_ENTRIES];
static unsigned s_pic_count;
static SRWLOCK s_pic_capture_lock = SRWLOCK_INIT;
typedef struct { uint64_t key; int overlay; uint8_t code[64]; } spu_pic_seen;
static spu_pic_seen s_pic_seen[8192];
static unsigned s_pic_seen_count;

static uint64_t spu_pic_key(const uint8_t* p)
{
    uint64_t a, b;
    memcpy(&a, p, 8);
    memcpy(&b, p + 8, 8);
    return a * UINT64_C(0x9E3779B97F4A7C15) ^
           (b + UINT64_C(0x632BE59BD9B4E019));
}

static int spu_pic_slot_cmp(const void* x, const void* y)
{
    const uint64_t a = ((const spu_pic_slot*)x)->key;
    const uint64_t b = ((const spu_pic_slot*)y)->key;
    return (a > b) - (a < b);
}

void spu_pic_register(const spu_pic_entry* entries, unsigned count,
                      const uint8_t* code, uint32_t code_size, int image_id)
{
    (void)image_id;
    if (!entries || !code) return;
    AcquireSRWLockExclusive(&s_pic_capture_lock);
    for (unsigned i = 0; i < count && s_pic_count < SPU_PIC_MAX_ENTRIES; ++i) {
        const spu_pic_entry* e = &entries[i];
        if (!e->func || e->addr > code_size || code_size - e->addr < 16u ||
            e->lo > e->addr || e->hi <= e->addr || e->hi > code_size ||
            e->hi - e->lo > SPU_PIC_MAX_SPAN)
            continue;
        s_pic[s_pic_count].key = spu_pic_key(code + e->addr);
        s_pic[s_pic_count].entry = e;
        s_pic[s_pic_count].code = code;
        ++s_pic_count;
    }
    qsort(s_pic, s_pic_count, sizeof s_pic[0], spu_pic_slot_cmp);
    ReleaseSRWLockExclusive(&s_pic_capture_lock);
}

/* Registration is completed synchronously by ar_m772_runtime_init before any
 * SPU worker starts. The sorted table is immutable during guest execution. */
static spu_fn spu_pic_lookup(spu_context* ctx)
{
    if (!s_pic_count) return NULL;
    const uint32_t pc = ctx->pc & SPU_LS_MASK & ~3u;
    if (pc > SPU_LS_SIZE - 16u) return NULL;
    const uint64_t key = spu_pic_key(ctx->ls + pc);
    unsigned lo = 0, hi = s_pic_count;
    while (lo < hi) {
        const unsigned mid = (lo + hi) / 2;
        if (s_pic[mid].key < key) lo = mid + 1; else hi = mid;
    }
    for (unsigned i = lo; i < s_pic_count && s_pic[i].key == key; ++i) {
        const spu_pic_entry* e = s_pic[i].entry;
        if (pc < e->addr - e->lo) continue;
        if (!spu_pic_entry_matches(ctx->ls, SPU_LS_SIZE, pc, s_pic[i].code,
                                   e->addr, e->lo, e->hi, e->ranges, e->nranges))
            continue;
        ctx->pic_base = (pc - e->addr) & SPU_LS_MASK;
        return (spu_fn)e->func;
    }
    return NULL;
}

/* Format is compatible with the PC port:
 *   <LS PC hex> <resident overlay decimal> <64 bytes as hex>
 * Capture only unresolved branches, so these are candidate runtime-copy
 * fragments and not a dump of every interpreted instruction. */
static void spu_pic_capture(const spu_context* ctx)
{
    const char* path = getenv("SPU_PIC_CAPTURE");
    if (!path || !*path) return;
    const uint32_t pc = ctx->pc & SPU_LS_MASK & ~3u;
    if (pc > SPU_LS_SIZE - 64u) return;
    const uint8_t* code = ctx->ls + pc;
    uint8_t any = 0;
    for (unsigned i = 0; i < 64; ++i) any |= code[i];
    if (!any) return;
    const uint64_t key = spu_pic_key(code) ^ spu_pic_key(code + 16) ^
                         spu_pic_key(code + 32) ^ spu_pic_key(code + 48);
    AcquireSRWLockExclusive(&s_pic_capture_lock);
    for (unsigned i = 0; i < s_pic_seen_count; ++i) {
        const spu_pic_seen* seen = &s_pic_seen[i];
        if (seen->key == key && seen->overlay == ctx->resident_ovl &&
            memcmp(seen->code, code, 64) == 0) {
            ReleaseSRWLockExclusive(&s_pic_capture_lock);
            return;
        }
    }
    if (s_pic_seen_count < sizeof(s_pic_seen) / sizeof(s_pic_seen[0])) {
        FILE* f = fopen(path, "a");
        if (f) {
            int ok = fprintf(f, "%05X %d ", pc, ctx->resident_ovl) > 0;
            for (unsigned i = 0; ok && i < 64; ++i)
                ok = fprintf(f, "%02X", code[i]) > 0;
            if (ok) ok = fputc('\n', f) != EOF;
            if (fclose(f) != 0) ok = 0;
            if (ok) {
                spu_pic_seen* seen = &s_pic_seen[s_pic_seen_count++];
                seen->key = key;
                seen->overlay = ctx->resident_ovl;
                memcpy(seen->code, code, 64);
                static unsigned logged;
                if (logged++ < 12)
                    fprintf(stderr, "[spu-pic] captured unresolved LS 0x%05X overlay=%d -> %s\n",
                            pc, ctx->resident_ovl, path);
            }
        }
    }
    ReleaseSRWLockExclusive(&s_pic_capture_lock);
}
'''


def patch(upstream: Path) -> None:
    context = upstream / "runtime/spu/spu_context.h"
    source = upstream / "runtime/spu/spu_channels.c"
    if not context.is_file() or not source.is_file():
        raise SystemExit(f"not a PS3Recomp source tree: {upstream}")

    text = context.read_text()
    if MARKER not in text:
        anchor = "    uint32_t drain_ret_pc;\n} spu_context;"
        replacement = "    uint32_t drain_ret_pc;\n    uint32_t pic_base; /* ASCENSION_M793_SPU_PIC_RUNTIME_V1 */\n} spu_context;\n\n#define SPU_PIC(ctx, a) (((ctx)->pic_base + (uint32_t)(a)) & SPU_LS_MASK)\n\ntypedef struct {\n    uint32_t addr, lo, hi;\n    void (*func)(spu_context*);\n    const uint32_t* ranges;\n    uint32_t nranges;\n} spu_pic_entry;\n\nvoid spu_pic_register(const spu_pic_entry*, unsigned, const uint8_t*, uint32_t, int);"
        if text.count(anchor) != 1:
            raise SystemExit("cannot anchor PIC context fields in pinned PS3Recomp")
        context.write_text(text.replace(anchor, replacement, 1))

    match_header = upstream / "runtime/spu/spu_pic_match.h"
    if not match_header.is_file():
        match_header.write_text(PIC_MATCH)

    text = source.read_text()
    if MARKER not in text:
        include_anchor = '#include "spu_interp.h"'
        if text.count(include_anchor) != 1:
            raise SystemExit("cannot anchor PIC matcher include in spu_channels.c")
        text = text.replace(include_anchor,
                            include_anchor + '\n#include "spu_pic_match.h"', 1)
        type_anchor = "typedef void (*spu_fn)(spu_context*);"
        if text.count(type_anchor) != 1:
            raise SystemExit("cannot anchor PIC registry in spu_channels.c")
        text = text.replace(type_anchor, type_anchor + "\n\n" + PIC_API, 1)
        high_anchor = "    if (!fn && !ctx->policy_mode && ctx->pc >= SPU_JM2_KERNEL_BASE) {"
        if text.count(high_anchor) != 1:
            raise SystemExit("cannot anchor unlifted SPU interpreter fallback")
        text = text.replace(high_anchor,
                            "    if (!fn) fn = spu_pic_lookup(ctx);\n" +
                            high_anchor + "\n        spu_pic_capture(ctx);", 1)
        microstep_anchor = "    if (spu_smc_microstep(ctx))\n        return;"
        if text.count(microstep_anchor) != 1:
            raise SystemExit("cannot anchor generic unlifted SPU capture")
        text = text.replace(microstep_anchor,
                            "    spu_pic_capture(ctx);\n" + microstep_anchor, 1)
        source.write_text(text)

    # Fail closed if a later upstream edit causes the runtime patch to land
    # incompletely: the app-side opt-in would otherwise look enabled but never
    # be consumed by this build.
    context_text = context.read_text()
    source_text = source.read_text()
    required = (MARKER, "spu_pic_register", "spu_pic_lookup", "spu_pic_capture",
                "spu_interp_run(ctx, p)")
    missing = [needle for needle in required
               if needle not in context_text and needle not in source_text]
    if missing:
        raise SystemExit(f"incomplete SPU interpreter/PIC runtime patch: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    patch(args.upstream.resolve())
    print("M7.94 SPU unlifted interpreter and PIC capture/dispatch runtime enabled")


if __name__ == "__main__":
    main()
