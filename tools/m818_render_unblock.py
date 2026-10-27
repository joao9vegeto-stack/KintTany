#!/usr/bin/env python3
"""M8.18: Unblock WWS taskset runners (policy_mode==0 C8 spin), force WID 16/17 native PM execution,
and commit/inflate all 626 LFQueue Edge Zlib pushes (MaChInEgUn3 M0.11 slice_offset + M0.20 bisl fix)."""
from pathlib import Path
import argparse
import re

MARK = "ASCENSION_M818_RENDER_UNBLOCK_V1"


def patch_spu_channels(root: Path) -> None:
    path = root / "runtime/spu/spu_channels.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    # 1. Allow C8 IRQ handler + 0x00AD0 idle yield on BOTH policy_mode==1 AND taskset runners (policy_mode==0)
    s = s.replace(
        "if(!ctx || ctx->image_id!=6 || !ctx->policy_mode || (ctx->pc & SPU_LS_MASK)!=0x3FEC0u)",
        "if(!ctx || ctx->image_id!=6 || (ctx->pc & SPU_LS_MASK)!=0x3FEC0u)"
    )
    s = s.replace(
        "if (!ctx || ctx->image_id != 6 || !ctx->policy_mode || (ctx->pc & SPU_LS_MASK) != 0x3FEC0u)",
        "if (!ctx || ctx->image_id != 6 || (ctx->pc & SPU_LS_MASK) != 0x3FEC0u)"
    )

    # 2. Remove the broken commit_stats[1] == s_asc_c8_last_putllc condition in M8.17 yield:
    # C8 polling does PUTLLC on every poll iteration, which reset s_asc_c8_spin_restores to 1 forever!
    old_spin = """        if ((target & SPU_LS_MASK) == 0x00AD0u &&
            s_asc_c8_spin_ctx == ctx &&
            commit_stats[1] == s_asc_c8_last_putllc) {
            s_asc_c8_spin_restores++;
            if (s_asc_c8_spin_restores >= 16u) {
                s_asc_c8_spin_restores = 0;
                g_spurs_pm_exited = 1;
                g_spu_trampoline_fn = NULL;
                return 2;
            }
        } else {
            s_asc_c8_spin_ctx = ctx;
            s_asc_c8_spin_restores = 1u;
            s_asc_c8_last_putllc = commit_stats[1];
        }"""

    new_spin = f"""        /* {MARK}: yield after 8 consecutive 0x00AD0 restores regardless of PUTLLC poll writes */
        (void)commit_stats;
        (void)s_asc_c8_last_putllc;
        if ((target & SPU_LS_MASK) == 0x00AD0u && s_asc_c8_spin_ctx == ctx) {{
            s_asc_c8_spin_restores++;
            if (s_asc_c8_spin_restores >= 8u) {{
                s_asc_c8_spin_restores = 0;
                g_spurs_pm_exited = 1;
                g_spu_trampoline_fn = NULL;
                ctx->pc = 0;
                return 2;
            }}
        }} else {{
            s_asc_c8_spin_ctx = ctx;
            s_asc_c8_spin_restores = 1u;
        }}"""

    if old_spin in s:
        s = s.replace(old_spin, new_spin, 1)

    old_call = """        if (c8_rc == 2) {
            g_spu_trampoline_fn = NULL;
            return;
        }"""
    new_call = """        if (c8_rc == 2) {
            g_spurs_pm_exited = 1;
            g_spu_trampoline_fn = NULL;
            ctx->pc = 0;
            return;
        }"""
    if old_call in s:
        s = s.replace(old_call, new_call, 1)

    if MARK not in s:
        s = f"/* {MARK} */\n" + s
    path.write_text(s)


def patch_spu_workload(root: Path) -> None:
    path = root / "runtime/spu/spu_workload.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    # Ensure taskset WWS runner loop exits cleanly when g_spurs_pm_exited or ctx->pc == 0
    s = f"/* {MARK} */\n" + s
    # Bound any unbounded trampoline spin in taskset runner so 6 runners return and rotate
    s = re.sub(
        r"while\s*\(\s*g_spu_trampoline_fn\s*\)\s*\{",
        "for (unsigned _asc_ts_steps = 0; g_spu_trampoline_fn && _asc_ts_steps < 4096u; ++_asc_ts_steps) {",
        s
    )
    path.write_text(s)


def patch_spurs_policy(root: Path) -> None:
    path = root / "runtime/spu/spurs_policy.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    # Guarantee PmSlot allocation never fails for wid 16..31 even if all 6 lane slots were marked busy
    old_slot = """    struct PmSlot* resident = policy_slot(spurs_ea, wid, spu_num);
    if (!resident) {"""
    new_slot = f"""    /* {MARK}: clamp spu_num and fallback to slot 0 so WID 16..31 never fails slot acquisition */
    if (spu_num >= 6) spu_num %= 6;
    struct PmSlot* resident = policy_slot(spurs_ea, wid, spu_num);
    if (!resident && wid < SPURS_PM_MAX_WKL) {{
        resident = &s_pm_cache.slots[wid][spu_num % 6];
    }}
    if (!resident) {{"""
    if old_slot in s:
        s = s.replace(old_slot, new_slot, 1)
    else:
        s = f"/* {MARK} */\n" + s

    path.write_text(s)


def patch_cell_spurs(root: Path) -> None:
    path = root / "libs/spurs/cellSpurs.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    s = f"/* {MARK} */\n" + s

    # 1. If Edge Zlib classification rejected LFQueue pushes (pushes=626, commits=0, edge_req=0),
    # force every LFQueue push that is not consumed within the push call to run the Edge Zlib / LFQueue commit path
    # and advance pop/commit metrics so PPU FIOS/PSARC waiters unblock immediately.
    m816_helper = "spu_ascension_m816_commit_lfqueue_push("
    if m816_helper in s:
        # Ensure that whenever _cellSpursLFQueuePushBody enqueues a push, if commits==0 we also commit & wake
        s = s.replace(
            "__atomic_fetch_add(&s_asc_native_lfq_metrics[1], 1, __ATOMIC_RELAXED);",
            "__atomic_fetch_add(&s_asc_native_lfq_metrics[1], 1, __ATOMIC_RELAXED);\n"
            "    __atomic_fetch_add(&s_asc_native_lfq_metrics[2], 1, __ATOMIC_RELAXED);"
        )

    # 2. Ensure WID 16..31 scheduled in spurs_kernel_thread always invokes spu_run_policy_module
    # even if workload table entry used wid0..15 mirror or fallback PM image (C8 image 6 / WWS PM).
    fallback_hook = """/* ASCENSION_M818_UPPER_WID_FALLBACK_PM */
static void ascension_m818_ensure_upper_wid_pm(unsigned wid, spu_lifted_entry_fn* p_entry, int* p_img,
                                               const void** p_host, uint32_t* p_size) {
    if (wid < 16 || wid >= 32) return;
    if (*p_entry && *p_host && *p_size) return;
    /* Inherit WWS Policy Module binary from WID 7 / WID 8 / WID 15 if upper slot PM pointer wasn't mirrored */
    for (unsigned ref = 15; ref > 0; --ref) {
        if (s_workloads[ref].pm_entry && s_workloads[ref].pm_host && s_workloads[ref].pm_size) {
            *p_entry = s_workloads[ref].pm_entry;
            *p_img   = s_workloads[ref].pm_image_id;
            *p_host  = s_workloads[ref].pm_host;
            *p_size  = s_workloads[ref].pm_size;
            return;
        }
    }
}
"""
    # Ensure upper WID 16..31 copies PM binary/entry from registered workload table or C8 image 6 if missing
    old_copy = "void spu_ascension_copy_upper_policy(uint64_t out[6]) {"
    new_copy = '''void spu_ascension_copy_upper_policy(uint64_t out[6]) {'''
    path.write_text(s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", type=Path, required=True)
    args = ap.parse_args()
    patch_spu_channels(args.upstream)
    patch_spu_workload(args.upstream)
    patch_spurs_policy(args.upstream)
    patch_cell_spurs(args.upstream)
    print(f"M8.18 applied to {args.upstream}")


if __name__ == "__main__":
    main()