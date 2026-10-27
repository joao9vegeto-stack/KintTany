#!/usr/bin/env python3
"""M8.17: break C8 policy-module 0x00AD0 idle IRQ spin so WID16/17 and LFQueue acquire SPU lanes."""
from pathlib import Path
import argparse

MARK = "ASCENSION_M817_C8_IDLE_POLL_YIELD_V1"


def once(source: str, old: str, new: str, label: str) -> str:
    n = source.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 anchor, found {n}: {old[:100]!r}")
    return source.replace(old, new, 1)


def patch_c8_irq_yield(root: Path) -> None:
    path = root / "runtime/spu/spu_channels.c"
    source = path.read_text(errors="replace")
    if MARK in source:
        return
    if "ASCENSION_M813_C8_IRQ_NATIVE_V1" not in source:
        raise SystemExit("M8.17 requires M8.13 C8 IRQ native handler in spu_channels.c")

    # Declare g_spurs_pm_exited and per-context/thread spin tracker before spu_ascension_run_c8_generated_irq
    old_fn = "int spu_ascension_run_c8_generated_irq(spu_context* ctx) {"
    new_fn = f"""/* {MARK}
 * When all 6 SPU workers enter C8 (image=6) with 0 ready tasks, the guest PM
 * polls in a tight save/restore IRQ loop returning to LS 0x00AD0 (179k+ calls)
 * without yielding the SPU slot, starving WID 16/17 and LFQueue consumers.
 * After a bounded number of consecutive 0x00AD0 restores in the same PM slice,
 * yield the policy module slice cleanly so the SPURS scheduler can rotate WIDs.
 */
extern _Thread_local int g_spurs_pm_exited;
static _Thread_local const spu_context* s_asc_c8_spin_ctx;
static _Thread_local uint32_t s_asc_c8_spin_restores;
static _Thread_local uint64_t s_asc_c8_last_putllc;
extern void spu_workload_copy_ascension_commit_metrics(uint64_t out[2]);

int spu_ascension_run_c8_generated_irq(spu_context* ctx) {{"""
    source = once(source, old_fn, new_fn, "M8.17 C8 IRQ function header")

    # Hook the restore completion path in spu_ascension_run_c8_generated_irq
    target_tail = """    ctx->pc=target;
    g_spu_trampoline_fn=spu_indirect_branch;
    return 1;
}"""
    replacement_tail = """    if (restoring) {
        uint64_t commit_stats[2] = {0, 0};
        spu_workload_copy_ascension_commit_metrics(commit_stats);
        if ((target & SPU_LS_MASK) == 0x00AD0u &&
            s_asc_c8_spin_ctx == ctx &&
            commit_stats[1] == s_asc_c8_last_putllc) {
            s_asc_c8_spin_restores++;
            if (s_asc_c8_spin_restores >= 16u) {
                s_asc_c8_spin_restores = 0;
                g_spurs_pm_exited = 1;
                return 2;
            }
        } else {
            s_asc_c8_spin_ctx = ctx;
            s_asc_c8_spin_restores = 1u;
            s_asc_c8_last_putllc = commit_stats[1];
        }
    }
    ctx->pc=target;
    g_spu_trampoline_fn=spu_indirect_branch;
    return 1;
}"""
    source = once(source, target_tail, replacement_tail, "M8.17 C8 restore yield tail")

    # Make the C8 dispatcher distinguish a policy-slice yield from a regular restore.
    old_call = """    if(ctx->pc==0x3FEC0u && spu_ascension_run_c8_generated_irq(ctx))
        return;"""
    new_call = """    if(ctx->pc==0x3FEC0u) {
        int c8_rc = spu_ascension_run_c8_generated_irq(ctx);
        if (c8_rc == 2) return;
        if (c8_rc) return;
    }"""
    source = once(source, old_call, new_call, "M8.17 C8 dispatcher yield result")

    path.write_text(source)


def patch_policy_loop(root: Path) -> None:
    """Ensure spurs_policy.c also respects g_spurs_pm_exited on C8 idle yield."""
    path = root / "runtime/spu/spurs_policy.c"
    source = path.read_text(errors="replace")
    if MARK in source:
        return
    old = "int result = g_spurs_pm_exited ? 0 : -2;"
    new = f"/* {MARK} */\n    int result = g_spurs_pm_exited ? 0 : -2;"
    source = once(source, old, new, "M8.17 spurs_policy marker")
    path.write_text(source)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", type=Path, required=True)
    args = ap.parse_args()
    patch_c8_irq_yield(args.upstream)
    patch_policy_loop(args.upstream)
    print(f"M8.17 applied to {args.upstream}")


if __name__ == "__main__":
    main()
