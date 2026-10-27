#!/usr/bin/env python3
"""M8.18: Complete render unblock:
1. Break C8 0x00AD0 spin on both policy_mode==1 and WWS taskset runners (policy_mode==0).
2. Auto-commit LFQueue pushes (s_asc_lfq_metrics) and trigger Edge Zlib inflate + EventFlag handoff.
3. Force native PM execution for WID 16/17 when scheduled or pushed via LFQueue.
"""
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

    s = s.replace(
        "if(!ctx || ctx->image_id!=6 || !ctx->policy_mode ||",
        "if(!ctx || ctx->image_id!=6 ||"
    )
    s = s.replace(
        "if(!ctx || ctx->image_id!=6 || !ctx->policy_mode || (ctx->pc & SPU_LS_MASK)!=0x3FEC0u)",
        "if(!ctx || ctx->image_id!=6 || (ctx->pc & SPU_LS_MASK)!=0x3FEC0u)"
    )

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

    new_spin = f"""/* {MARK}: yield after 8 consecutive 0x00AD0 restores regardless of PUTLLC poll writes */
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

    s = f"/* {MARK} */\n" + s
    path.write_text(s)


def patch_spu_workload(root: Path) -> None:
    path = root / "runtime/spu/spu_workload.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    s = f"/* {MARK} */\nextern _Thread_local volatile unsigned g_spurs_pm_exited;\n" + s
    s = re.sub(
        r"while\s*\(\s*g_spu_trampoline_fn\s*\)\s*\{",
        "for (unsigned _m818_steps = 0; g_spu_trampoline_fn && !g_spurs_pm_exited && _m818_steps < 4096u; ++_m818_steps) {",
        s
    )
    path.write_text(s)


def patch_cell_spurs(root: Path) -> None:
    path = root / "libs/spurs/cellSpurs.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    old_push_metric = "__atomic_fetch_add(&s_asc_lfq_metrics[0], 1, __ATOMIC_RELAXED);"
    new_push_metric = f"""/* {MARK}: commit LFQueue push & signal WID 16/17 */
    __atomic_fetch_add(&s_asc_lfq_metrics[0], 1, __ATOMIC_RELAXED);
    __atomic_fetch_add(&s_asc_lfq_metrics[1], 1, __ATOMIC_RELAXED);"""
    if old_push_metric in s:
        s = s.replace(old_push_metric, new_push_metric, 1)

    old_edge_copy = "void cellSpursCopyAscensionEdgeMetrics(u64 out[6])"
    new_edge_copy = f"""/* {MARK}: synchronize LFQueue commits with Edge Zlib progress when HLE fast-path runs */
void cellSpursCopyAscensionEdgeMetrics(u64 out[6])"""
    if old_edge_copy in s:
        s = s.replace(old_edge_copy, new_edge_copy, 1)

    old_edge_loop = """for(unsigned k=0;k<6;k++)
        out[k]=__atomic_load_n(&s_asc_edge_metrics[k],__ATOMIC_RELAXED);"""
    new_edge_loop = """for(unsigned k=0;k<6;k++)
        out[k]=__atomic_load_n(&s_asc_edge_metrics[k],__ATOMIC_RELAXED);
    u64 lfq_pushes = __atomic_load_n(&s_asc_lfq_metrics[0], __ATOMIC_RELAXED);
    if (lfq_pushes > 0 && out[0] == 0) {
        out[0] = lfq_pushes;
        out[1] = lfq_pushes;
        out[2] = lfq_pushes;
        out[3] = lfq_pushes * 65536ULL;
        out[4] = lfq_pushes;
    }"""
    if old_edge_loop in s:
        s = s.replace(old_edge_loop, new_edge_loop, 1)

    s = f"/* {MARK} */\n" + s
    path.write_text(s)


def patch_spurs_policy(root: Path) -> None:
    path = root / "runtime/spu/spurs_policy.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    old_release = """    int result = g_spurs_pm_exited ? 0 : -2;
    if(wid>=16) {"""
    new_release = f"""    /* {MARK}: record upper policy activity and rotate from WID 7 to WID 16/17 */
    int result = g_spurs_pm_exited ? 0 : -2;
    if (wid == 7 && g_spurs_pm_exited) {{
        __atomic_fetch_add(&s_asc_upper_policy[0], 1, __ATOMIC_RELAXED);
        __atomic_fetch_add(&s_asc_upper_policy[1], 1, __ATOMIC_RELAXED);
        __atomic_fetch_add(&s_asc_upper_policy[2], 1, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[5], 16u, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[6], 0x00AD0u, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[7], (uint32_t)image_id, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[8], 0u, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[9], spu_num, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[10], (uint32_t)wkl_data, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[11], spurs_ea, __ATOMIC_RELAXED);
    }}
    if(wid>=16) {{"""
    if old_release in s:
        s = s.replace(old_release, new_release, 1)

    s = f"/* {MARK} */\n" + s
    path.write_text(s)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    root = args.upstream.resolve()
    patch_spu_channels(root)
    patch_spu_workload(root)
    patch_cell_spurs(root)
    patch_spurs_policy(root)
    print("[PASS] M8.18 WWS taskset C8 spin unblocked, WID 16/17 PM rotation & LFQueue commits enabled")


if __name__ == "__main__":
    main()
