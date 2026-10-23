#!/usr/bin/env python3
"""Compile the patched production SPU drain and verify interpreter returns."""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import tempfile

from enable_ios_spu_pic_runtime import patch_interpreter_rejoin


def c_function(source: str, name: str) -> str:
    match = re.search(r"\b(?:static\s+)?(?:void|int)\s+" + re.escape(name) +
                      r"\s*\([^;]*\)\s*\{", source)
    if not match:
        raise AssertionError(f"production function not found: {name}")
    start = source.index("{", match.start())
    depth = 1
    pos = start + 1
    while depth:
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
        pos += 1
    signature_start = source.rfind("\n", 0, match.start()) + 1
    return source[signature_start:pos]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=pathlib.Path, required=True)
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    patch_interpreter_rejoin(upstream)

    channels = (upstream / "runtime/spu/spu_channels.c").read_text(errors="replace")
    drain_path = upstream / "runtime/spu/spu_drain.c"
    drain = drain_path.read_text(errors="replace")
    assert "ASCENSION_M802_SPU_INTERPRETER_REJOIN_CHANNELS_V1" in channels
    assert "ASCENSION_M802_SPU_INTERPRETER_REJOIN_HELPER_V1" in channels
    assert "SPU_REJOIN_CALL" in channels
    assert "spu_drain_interp(ctx, return_pc)" in channels
    assert channels.count("spu_rejoin_interpreted_lift(ctx, return_pc)") >= 3
    assert "ASCENSION_M802_SPU_INTERPRETER_REJOIN_DRAIN_V1" in drain
    assert "g_spu_drain_anyret = anyret ? (int)ctx->host_depth : 0;" in drain
    wws_fallback = channels.split("ASCENSION_M795_WWS_INTERPRETER_FALLBACK_V1", 1)[1]
    assert "uint32_t p = ctx->pc & SPU_LS_MASK & ~3u;" in wws_fallback
    assert "const uint32_t p = ctx->pc & SPU_LS_MASK & ~3u;" not in wws_fallback

    # Applying the patcher twice must leave the generated runtime unchanged.
    before = drain_path.read_bytes()
    patch_interpreter_rejoin(upstream)
    assert drain_path.read_bytes() == before, "M8.02 SPU drain patch is not idempotent"

    production = c_function(channels, "spu_rejoin_interpreted_lift") + "\n" + "\n".join(
        c_function(drain, name) for name in
        ("spu_drain_loop", "spu_drain_call", "spu_drain_interp"))
    fixture = r'''#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define SPU_LS_MASK 0x3FFFFu
#define SPU_STATUS_RUNNING 1u
#define SPU_THREAD_LOCAL _Thread_local
typedef struct spu_context spu_context;
typedef void (*spu_drain_fn)(spu_context*);
typedef void (*spu_lifted_fn)(spu_context*);
typedef struct spu_irq_frame {
    jmp_buf env;
    struct spu_irq_frame* prev;
    uint32_t depth;
    int image_id;
} spu_irq_frame;
struct spu_context {
    uint32_t pc, host_depth, drain_ret_pc, event_status, event_mask, status;
    int image_id, resident_ovl, int_enable;
    void* irq_frame;
};

SPU_THREAD_LOCAL spu_drain_fn g_spu_trampoline_fn;
SPU_THREAD_LOCAL int g_spu_drain_anyret;
static unsigned launches, restarts;
static void second_hop(spu_context* ctx);
void spu_drain_interp(spu_context* ctx, uint32_t return_pc);
void spu_drain_call(spu_context* ctx, uint32_t return_pc);
static unsigned lifted_calls;
static void target_lift(spu_context* ctx) {
    assert(g_spu_drain_anyret == (int)ctx->host_depth);
    ++lifted_calls; ctx->pc = 0x500;
}
static void spu_indirect_branch(spu_context* ctx) { target_lift(ctx); }
void spu_depth_guard(spu_context* ctx) { (void)ctx; }
void yz_lockstep_tick(spu_context* ctx) { (void)ctx; }
void spu_task_launch_check(spu_context* ctx, void* fn) {
    (void)ctx; (void)fn; ++launches;
}
spu_drain_fn spu_take_interrupt(spu_context* ctx, spu_drain_fn fn) {
    (void)ctx; return fn;
}
spu_drain_fn spu_lookup(uint32_t pc, int image_id) {
    (void)pc; (void)image_id; return NULL;
}
spu_lifted_fn spu_lifted_lookup(const spu_context* ctx, uint32_t pc) {
    (void)ctx; return pc == 0x200 ? target_lift : NULL;
}
void spu_img_restore(spu_context* ctx, int32_t image_id) {
    ctx->image_id = image_id;
}
void spu_restart_dispatch(spu_context* ctx) { (void)ctx; ++restarts; }

static unsigned first_calls, second_calls, interpreter_returns;
static void first_hop(spu_context* ctx) {
    ++first_calls; ctx->pc = 0x500; g_spu_trampoline_fn = second_hop;
}
static void second_hop(spu_context* ctx) {
    ++second_calls; ctx->pc = 0x900;
}
static void returns_to_interpreter(spu_context* ctx) {
    assert(g_spu_drain_anyret == (int)ctx->host_depth);
    ++interpreter_returns; ctx->pc = 0x500;
}
static void calls_interpreter_drain(spu_context* ctx) {
    assert(g_spu_drain_anyret == 0);
    g_spu_trampoline_fn = returns_to_interpreter;
    spu_drain_interp(ctx, 0x888);
    assert(g_spu_drain_anyret == 0);
    ctx->pc = 0x900;
}

/* PRODUCTION_FUNCTIONS */

int main(void) {
    spu_context ctx = {0};
    ctx.image_id = 1;
    ctx.host_depth = 7;

    /* An interpreter-owned drain ends at the first host return, even though
     * that PC is not the enclosing call's return address. */
    g_spu_trampoline_fn = returns_to_interpreter;
    spu_drain_interp(&ctx, 0x900);
    assert(interpreter_returns == 1 && ctx.pc == 0x500);
    assert(ctx.drain_ret_pc == 0 && g_spu_drain_anyret == 0);

    /* A normal lifted call still follows trampoline hops until its explicit
     * guest return PC. */
    ctx.pc = 0x100;
    g_spu_trampoline_fn = first_hop;
    spu_drain_call(&ctx, 0x900);
    assert(first_calls == 1 && second_calls == 1 && ctx.pc == 0x900);
    assert(g_spu_drain_anyret == 0);

    /* Nested interpreter drains restore the outer drain mode on return. */
    ctx.pc = 0x100;
    g_spu_trampoline_fn = calls_interpreter_drain;
    spu_drain_call(&ctx, 0x900);
    assert(interpreter_returns == 2 && ctx.pc == 0x900);
    assert(g_spu_drain_anyret == 0 && restarts == 0 && launches >= 4);

    /* The production helper must actually dispatch a lift through the
     * interpreter-owned drain, then restore image, depth and return PC. */
    setenv("SPU_REJOIN_CALL", "1", 1);
    ctx.pc = 0x200; ctx.status = SPU_STATUS_RUNNING; ctx.host_depth = 7;
    ctx.drain_ret_pc = 0x900;
    assert(spu_rejoin_interpreted_lift(&ctx, 0x900) == 1);
    assert(lifted_calls == 1 && ctx.pc == 0x500 && ctx.host_depth == 7);
    assert(ctx.drain_ret_pc == 0x900 && g_spu_drain_anyret == 0);
    g_spu_drain_anyret = (int)ctx.host_depth;
    assert(spu_rejoin_interpreted_lift(&ctx, 0x900) == 0);
    assert(lifted_calls == 1);
    g_spu_drain_anyret = 0;
    puts("M8.02 SPU interpreter rejoin drain: first-host-return, call return, and nested-state tests PASS");
    return 0;
}
'''
    source = fixture.replace("/* PRODUCTION_FUNCTIONS */", production)
    with tempfile.TemporaryDirectory(prefix="m802-spu-rejoin-") as tmp:
        c_file = pathlib.Path(tmp) / "test.c"
        binary = pathlib.Path(tmp) / "test"
        c_file.write_text(source)
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu17", "-O2", "-Wall",
                        "-Wextra", "-Werror", str(c_file), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
