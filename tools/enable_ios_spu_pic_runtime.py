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
WWS_INTERP_MARKER = "ASCENSION_M795_WWS_INTERPRETER_FALLBACK_V1"
INTERP_SLICE_MARKER = "ASCENSION_M795_SPU_INTERPRETER_SLICE_V1"
REJOIN_CHANNEL_MARKER = "ASCENSION_M802_SPU_INTERPRETER_REJOIN_CHANNELS_V1"
REJOIN_HELPER_MARKER = "ASCENSION_M802_SPU_INTERPRETER_REJOIN_HELPER_V1"
REJOIN_DRAIN_MARKER = "ASCENSION_M802_SPU_INTERPRETER_REJOIN_DRAIN_V1"

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


def patch_interpreter_rejoin(upstream: Path) -> None:
    """Drain lifted functions reached by the SPU interpreter on its own stack.

    Without this handoff, a lifted function reached from interpreted code can
    return into the enclosing WWS drain. That drain treats the return as a
    dispatcher restart and loses the interpreter's continuation. The PC port
    fixes this with SPU_REJOIN_CALL; keep the same behavior on iOS.
    """
    channels = upstream / "runtime/spu/spu_channels.c"
    drain = upstream / "runtime/spu/spu_drain.c"
    if not channels.is_file() or not drain.is_file():
        raise SystemExit(f"missing PS3Recomp SPU drain sources: {upstream}")

    source = channels.read_text(errors="replace")
    if REJOIN_CHANNEL_MARKER not in source:
        run_anchor = "    g_spu_trampoline_fn = 0;                        /* no stale transfer pending */\n"
        run_replacement = run_anchor + '''    /* ASCENSION_M802_SPU_INTERPRETER_REJOIN_CHANNELS_V1
     * An interpreter drain is a continuation owned by the current SPU run.
     * Do not let it leak across a nested top-level job or a stack reset. */
    extern SPU_THREAD_LOCAL int g_spu_drain_anyret;
    const int asc_outer_anyret = g_spu_drain_anyret;
    g_spu_drain_anyret = 0;
'''
        if source.count(run_anchor) != 1:
            raise SystemExit("M8.02 could not anchor SPU run's nested interpreter-drain state")
        source = source.replace(run_anchor, run_replacement, 1)

        reset_anchor = "        ctx->host_depth = 0;\n        g_spu_trampoline_fn = 0;\n        spu_indirect_branch(ctx);"
        reset_replacement = "        ctx->host_depth = 0;\n        g_spu_trampoline_fn = 0;\n        g_spu_drain_anyret = 0;\n        spu_indirect_branch(ctx);"
        if source.count(reset_anchor) != 1:
            raise SystemExit("M8.02 could not anchor SPU stack-reset cleanup")
        source = source.replace(reset_anchor, reset_replacement, 1)

        exit_anchor = "    if (outer_armed) memcpy(s_spu_halt_env, outer_env, sizeof(jmp_buf));\n    return halted;"
        exit_replacement = "    if (outer_armed) memcpy(s_spu_halt_env, outer_env, sizeof(jmp_buf));\n    g_spu_drain_anyret = asc_outer_anyret;\n    return halted;"
        if source.count(exit_anchor) != 1:
            raise SystemExit("M8.02 could not anchor SPU run's interpreter-drain cleanup")
        source = source.replace(exit_anchor, exit_replacement, 1)

        helper_anchor = "static int spu_smc_microstep(spu_context* ctx)\n{"
        helper_replacement = r'''/* ASCENSION_M802_SPU_INTERPRETER_REJOIN_HELPER_V1
 * Run a lifted target inside a drain owned by the interpreter that reached
 * it. Return 1 when the guest can be interpreted again, 2 when it stopped,
 * and 0 when the caller should keep its existing dispatch behavior. */
static int spu_rejoin_interpreted_lift(spu_context* ctx, uint32_t return_pc)
{
    static int s_rejoin = -1;
    int rejoin_enabled = __atomic_load_n(&s_rejoin, __ATOMIC_ACQUIRE);
    if (rejoin_enabled < 0) {
        const char* e = getenv("SPU_REJOIN_CALL");
        rejoin_enabled = e && *e == '1';
        __atomic_store_n(&s_rejoin, rejoin_enabled, __ATOMIC_RELEASE);
    }
    extern SPU_THREAD_LOCAL int g_spu_drain_anyret;
    extern void spu_drain_interp(spu_context*, uint32_t);
    if (!rejoin_enabled || g_spu_drain_anyret == (int)ctx->host_depth ||
        ctx->image_id < 0 || !(ctx->status & SPU_STATUS_RUNNING) ||
        (return_pc && (ctx->pc & SPU_LS_MASK) == return_pc) ||
        !spu_lifted_lookup(ctx, ctx->pc))
        return 0;

    const int32_t saved_image = (int32_t)ctx->image_id;
    ctx->host_depth++;
    g_spu_trampoline_fn = spu_indirect_branch;
    spu_drain_interp(ctx, return_pc);
    ctx->host_depth--;
    spu_img_restore(ctx, saved_image);
    ctx->drain_ret_pc = return_pc;
    return (ctx->status & SPU_STATUS_RUNNING) ? 1 : 2;
}

static int spu_smc_microstep(spu_context* ctx)
{'''
        if source.count(helper_anchor) != 1:
            raise SystemExit("M8.02 could not anchor interpreter rejoin helper")
        source = source.replace(helper_anchor, helper_replacement, 1)

        interp_anchor = "        uint32_t result = spu_interp_run_until(ctx, pc, return_pc);\n        /* A live interpreter rejoin is a transfer, not a host return."
        interp_replacement = '''        uint32_t result;
    interp_again:
        result = spu_interp_run_until(ctx, pc, return_pc);
        { const int rejoin = spu_rejoin_interpreted_lift(ctx, return_pc);
          if (rejoin == 1) { pc = ctx->pc & SPU_LS_MASK; goto interp_again; }
          if (rejoin == 2) return 1; }
        /* A live interpreter rejoin is a transfer, not a host return.'''
        if source.count(interp_anchor) != 1:
            raise SystemExit("M8.02 could not anchor lifted-function interpreter handoff")
        source = source.replace(interp_anchor, interp_replacement, 1)

        high_interp_anchor = "              spu_interp_run(ctx, p);\n              return;"
        high_interp_replacement = '''              const uint32_t return_pc = ctx->drain_ret_pc;
              uint32_t interp_pc = p;
          ascension_unlifted_interp_again:
              (void)spu_interp_run_until(ctx, interp_pc, return_pc);
              { const int rejoin = spu_rejoin_interpreted_lift(ctx, return_pc);
                if (rejoin == 1) { interp_pc = ctx->pc & SPU_LS_MASK; goto ascension_unlifted_interp_again; }
                if (rejoin == 2) return; }
              /* Keep live interpreter rejoin working when the call-return
               * drain is disabled, and resume it through the dispatcher. */
              if (ctx->image_id >= 0 && (ctx->status & SPU_STATUS_RUNNING) &&
                  (!return_pc || (ctx->pc & SPU_LS_MASK) != return_pc) &&
                  spu_lifted_lookup(ctx, ctx->pc))
                  g_spu_trampoline_fn = spu_indirect_branch;
              return;'''
        if source.count(high_interp_anchor) != 1:
            raise SystemExit("M8.02 could not anchor high-address unlifted interpreter handoff")
        source = source.replace(high_interp_anchor, high_interp_replacement, 1)
        channels.write_text(source)

    source = channels.read_text(errors="replace")
    if REJOIN_CHANNEL_MARKER not in source:
        raise SystemExit("M8.02 SPU interpreter rejoin patch did not apply to spu_channels.c")

    source = drain.read_text(errors="replace")
    if REJOIN_DRAIN_MARKER not in source:
        entry_anchor = "void spu_drain_call(spu_context* ctx, uint32_t return_pc)\n{\n    spu_depth_guard(ctx);"
        entry_replacement = '''/* ASCENSION_M802_SPU_INTERPRETER_REJOIN_DRAIN_V1
 * Host depth of the current interpreter-owned drain; zero when the innermost
 * active drain is a normal lifted call. */
SPU_THREAD_LOCAL int g_spu_drain_anyret;

static void spu_drain_loop(spu_context* ctx, uint32_t return_pc, int anyret)
{
    spu_depth_guard(ctx);
    const int outer_anyret = g_spu_drain_anyret;'''
        if source.count(entry_anchor) != 1:
            raise SystemExit("M8.02 could not anchor the shared SPU drain loop")
        source = source.replace(entry_anchor, entry_replacement, 1)

        macro_anchor = "#define SPU_DRAIN_POP_IRQ() do { if (ctx->irq_frame == &f) ctx->irq_frame = f.prev; ctx->drain_ret_pc = 0; } while (0)"
        macro_replacement = "#define SPU_DRAIN_POP_IRQ() do { if (ctx->irq_frame == &f) ctx->irq_frame = f.prev; ctx->drain_ret_pc = 0; g_spu_drain_anyret = outer_anyret; } while (0)"
        if source.count(macro_anchor) != 1:
            raise SystemExit("M8.02 could not anchor SPU drain cleanup")
        source = source.replace(macro_anchor, macro_replacement, 1)

        return_anchor = "            if (g_spu_trampoline_fn == spu_indirect_branch &&\n                (ctx->pc & SPU_LS_MASK) == (return_pc & SPU_LS_MASK)) {"
        return_replacement = "            if (g_spu_trampoline_fn == spu_indirect_branch && (return_pc || !anyret) &&\n                (ctx->pc & SPU_LS_MASK) == (return_pc & SPU_LS_MASK)) {"
        if source.count(return_anchor) != 1:
            raise SystemExit("M8.02 could not anchor drain trampoline return test")
        source = source.replace(return_anchor, return_replacement, 1)

        set_anyret_anchor = "            ctx->drain_ret_pc = return_pc & SPU_LS_MASK;   /* re-set: a nested drain changed it */"
        set_anyret_replacement = set_anyret_anchor + "\n            g_spu_drain_anyret = anyret ? (int)ctx->host_depth : 0;"
        if source.count(set_anyret_anchor) != 1:
            raise SystemExit("M8.02 could not anchor SPU drain continuation tracking")
        source = source.replace(set_anyret_anchor, set_anyret_replacement, 1)

        irq_anchor = "                        ctx->image_id = f.image_id;\n                        g_spu_trampoline_fn = spu_indirect_branch;"
        irq_replacement = "                        ctx->image_id = f.image_id;\n                        g_spu_drain_anyret = anyret ? (int)ctx->host_depth : 0;\n                        g_spu_trampoline_fn = spu_indirect_branch;"
        if source.count(irq_anchor) != 1:
            raise SystemExit("M8.02 could not anchor SPU interrupt-drain rejoin")
        source = source.replace(irq_anchor, irq_replacement, 1)

        pc_return_anchor = "        if ((ctx->pc & SPU_LS_MASK) == (return_pc & SPU_LS_MASK)) {"
        pc_return_replacement = "        if ((anyret && ctx->irq_frame != &f) ||\n            (ctx->pc & SPU_LS_MASK) == (return_pc & SPU_LS_MASK)) {"
        if source.count(pc_return_anchor) != 1:
            raise SystemExit("M8.02 could not anchor SPU drain host-return condition")
        source = source.replace(pc_return_anchor, pc_return_replacement, 1)

        wrapper_anchor = "#undef SPU_DRAIN_POP_IRQ\n}"
        wrapper_replacement = '''#undef SPU_DRAIN_POP_IRQ
}

void spu_drain_call(spu_context* ctx, uint32_t return_pc)
{
    spu_drain_loop(ctx, return_pc, 0);
}

/* Stop at the first host return so the owning SPU interpreter can continue. */
void spu_drain_interp(spu_context* ctx, uint32_t return_pc)
{
    spu_drain_loop(ctx, return_pc, 1);
}'''
        if source.count(wrapper_anchor) != 1:
            raise SystemExit("M8.02 could not anchor SPU drain entry wrappers")
        source = source.replace(wrapper_anchor, wrapper_replacement, 1)
        drain.write_text(source)

    source = drain.read_text(errors="replace")
    required_drain = (
        REJOIN_DRAIN_MARKER, "g_spu_drain_anyret", "spu_drain_interp",
        "spu_drain_loop(spu_context* ctx, uint32_t return_pc, int anyret)",
    )
    missing = [needle for needle in required_drain if needle not in source]
    if missing:
        raise SystemExit(f"incomplete M8.02 SPU drain rejoin patch: {missing}")
    source = channels.read_text(errors="replace")
    required_channels = (
        REJOIN_CHANNEL_MARKER, REJOIN_HELPER_MARKER, "SPU_REJOIN_CALL",
        "interp_again:", "spu_rejoin_interpreted_lift(ctx, return_pc)",
        "ascension_unlifted_interp_again:",
        "g_spu_drain_anyret = asc_outer_anyret",
    )
    missing = [needle for needle in required_channels if needle not in source]
    if missing:
        raise SystemExit(f"incomplete M8.02 SPU interpreter rejoin patch: {missing}")


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

    # The PC port enables SPU_INTERP_UNLIFTED for generated/copy-relocated
    # code. In the pinned runtime, the env-gated whole-image fallback excludes
    # policy contexts. A WWS policy miss therefore reaches the limited SMC
    # microstep path first; route that miss through the same full interpreter
    # when opted in, after native/PIC lookups have failed.
    text = source.read_text()
    if WWS_INTERP_MARKER not in text:
        anchor = "    spu_pic_capture(ctx);\n    if (spu_smc_microstep(ctx))\n        return;"
        fallback = r'''    spu_pic_capture(ctx);
    /* ASCENSION_M795_WWS_INTERPRETER_FALLBACK_V1
     * Ascension's WWS policy generates small SPU stubs in LS at runtime. The
     * generic SPU_INTERP_UNLIFTED branch excludes policy_mode, so an unresolved
     * WWS instruction otherwise reaches only the partial SMC microstep path.
     * Keep static lifts and exact-byte PIC lifts first; interpret the remaining
     * nonzero WWS instruction stream until it reaches a lifted function, stop,
     * or this host call's return PC. */
    if (!fn && ctx->policy_mode && spu_workload_is_wws_pm_image(ctx->image_id)) {
        static int s_wws_interp = -1;
        int interp = __atomic_load_n(&s_wws_interp, __ATOMIC_ACQUIRE);
        if (interp < 0) {
            const char* e = getenv("SPU_INTERP_UNLIFTED");
            interp = e && *e != '0';
            __atomic_store_n(&s_wws_interp, interp, __ATOMIC_RELEASE);
        }
        uint32_t p = ctx->pc & SPU_LS_MASK & ~3u;
        const uint32_t w0 = ((uint32_t)ctx->ls[p] << 24) |
                            ((uint32_t)ctx->ls[p + 1] << 16) |
                            ((uint32_t)ctx->ls[p + 2] << 8) | ctx->ls[p + 3];
        if (interp && w0) {
            const uint32_t return_pc = ctx->drain_ret_pc;
            uint32_t result;
            for (;;) {
                result = spu_interp_run_until_budget(ctx, p, return_pc, 4096);
                const int rejoin = spu_rejoin_interpreted_lift(ctx, return_pc);
                if (rejoin == 1) { p = ctx->pc & SPU_LS_MASK; continue; }
                if (rejoin == 2) break;
                break;
            }
            if (ctx->status & SPU_STATUS_RUNNING) {
                if (!return_pc || (ctx->pc & SPU_LS_MASK) != return_pc)
                    g_spu_trampoline_fn = spu_indirect_branch;
            }
            /* The budget returns at a lift, stop, caller return, or after
             * 4096 instructions. Re-enter through the trampoline on a live
             * WWS PC so long guest routines remain resumable and bounded. */
            (void)result;
            return;
        }
    }
    if (spu_smc_microstep(ctx))
        return;'''
        if text.count(anchor) != 1:
            raise SystemExit("cannot anchor complete interpreter fallback for WWS policy misses")
        text = text.replace(anchor, fallback, 1)
        source.write_text(text)

    # Fail closed if a later upstream edit causes the runtime patch to land
    # incompletely: the app-side opt-in would otherwise look enabled but never
    # be consumed by this build.
    context_text = context.read_text()
    source_text = source.read_text()
    required = (MARKER, "spu_pic_register", "spu_pic_lookup", "spu_pic_capture",
                "spu_interp_run_until_budget(ctx, p, return_pc, 4096)")
    missing = [needle for needle in required
               if needle not in context_text and needle not in source_text]
    if WWS_INTERP_MARKER not in source_text:
        missing.append(WWS_INTERP_MARKER)
    if missing:
        raise SystemExit(f"incomplete SPU interpreter/PIC runtime patch: {missing}")

    interp_header = upstream / "runtime/spu/spu_interp.h"
    interp_source = upstream / "runtime/spu/spu_interp.c"
    if not interp_header.is_file() or not interp_source.is_file():
        raise SystemExit(f"missing PS3Recomp SPU interpreter sources: {upstream}")

    # WWS interpretation yields to the existing trampoline after a fixed
    # instruction quantum. The caller preserves the live PC/register state and
    # resumes from there, so long dynamic routines do not monopolize one host
    # call or grow the host stack.
    interp_text = interp_source.read_text()
    if INTERP_SLICE_MARKER not in interp_text:
        function_anchor = "uint32_t spu_interp_run_until(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa) {"
        function_replacement = '''uint32_t spu_interp_run_until(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa) {
    return spu_interp_run_until_budget(ctx, start_lsa, stop_lsa, 0);
}

/* ASCENSION_M795_SPU_INTERPRETER_SLICE_V1 */
uint32_t spu_interp_run_until_budget(spu_context* ctx, uint32_t start_lsa,
                                     uint32_t stop_lsa, uint64_t step_budget) {'''
        if interp_text.count(function_anchor) != 1:
            raise SystemExit("cannot anchor bounded SPU interpreter in spu_interp.c")
        interp_text = interp_text.replace(function_anchor, function_replacement, 1)
        rejoin_anchor = "        if (ctx->image_id >= 0 && ((stop_lsa && ctx->pc == stop_lsa) || spu_lifted_lookup(ctx, ctx->pc))) { g_spu_interp_steps = steps; g_spu_interp_last_pc = ctx->pc; return ctx->pc; }  /* rejoin fast path */"
        budget_check = rejoin_anchor + '''
        if (step_budget && steps >= step_budget) {
            g_spu_interp_steps = steps;
            g_spu_interp_last_pc = ctx->pc;
            return ctx->pc;
        }'''
        if interp_text.count(rejoin_anchor) != 1:
            raise SystemExit("cannot anchor SPU interpreter instruction budget")
        interp_text = interp_text.replace(rejoin_anchor, budget_check, 1)
        interp_source.write_text(interp_text)

    header_text = interp_header.read_text()
    budget_declaration = "uint32_t spu_interp_run_until_budget(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa, uint64_t step_budget);"
    if budget_declaration not in header_text:
        header_anchor = "uint32_t spu_interp_run_until(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa);"
        if header_text.count(header_anchor) != 1:
            raise SystemExit("cannot anchor bounded SPU interpreter declaration")
        header_text = header_text.replace(
            header_anchor,
            header_anchor + "\n/* Budgeted variant returns with live state after at most step_budget instructions (0 = unlimited). */\n" + budget_declaration,
            1)
        interp_header.write_text(header_text)

    if INTERP_SLICE_MARKER not in interp_source.read_text():
        raise SystemExit("bounded SPU interpreter patch did not apply")

    patch_interpreter_rejoin(upstream)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    patch(args.upstream.resolve())
    print("M7.95 full WWS SPU interpreter/PIC plus M8.02 interpreter-to-lifted rejoin enabled")


if __name__ == "__main__":
    main()
