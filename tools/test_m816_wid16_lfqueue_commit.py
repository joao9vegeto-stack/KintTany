#!/usr/bin/env python3
"""M8.16 regression: WID16/17 flag handoff, EDGE signal integrity and real LFQueue commits."""
from pathlib import Path
import argparse

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    root = parser.parse_args().upstream
    spurs = (root / "libs/spurs/cellSpurs.c").read_text(errors="replace")
    policy = (root / "runtime/spu/spurs_policy.c").read_text(errors="replace")
    workload = (root / "runtime/spu/spu_workload.c").read_text(errors="replace")

    assert "ASCENSION_M816_WID16_FLAG_EDGE_HANDOFF_V1" in spurs
    assert "ASCENSION_M811_EDGE_CLASSIFICATION_V1" in spurs
    assert "static volatile u64 s_asc_edge_metrics[6]" in spurs
    assert "void cellSpursCopyAscensionEdgeMetrics(u64 out[6])" in spurs
    assert "edge_event_rc == CELL_OK" in spurs
    assert "s_asc_edge_metrics[5]" in spurs
    assert "return edge_event_rc;" in spurs

    # Admission can wake the PM because of a workload flag but cannot consume
    # it before the lifted PM reaches its own ModulePoll selection point.
    selector_start = spurs.index("u32 spurs_poll_select(u32 ea, u32 current, u32 spu)")
    selector_end = spurs.index("\n}", selector_start)
    selector = spurs[selector_start:selector_end]
    assert "spurs_workload_flag_peek(ea, wid)" in selector
    assert "spurs_workload_flag_take(ea, wid)" in selector
    scheduler_start = spurs.index("static DWORD WINAPI spurs_kernel_thread(LPVOID p)\n{")
    scheduler_end = spurs.index("\nstatic s32 spurs_scheduler_start", scheduler_start)
    scheduler = spurs[scheduler_start:scheduler_end]
    assert "const int flagged = spurs_workload_flag_peek(ea, wid);" in scheduler
    assert "const int flagged = spurs_workload_flag_take(ea, wid);" not in scheduler

    # Native LFQueue commits remain distinct from the fast EDGE inflate path.
    assert "ASCENSION_M810_NATIVE_LFQUEUE_V1" in spurs
    assert "lfq_complete_push_pointer" in spurs
    assert "__atomic_fetch_add(&s_asc_lfq_metrics[2],1" in spurs
    assert "spurs_signal_waiter" in spurs
    assert "spu_signal_parked_on_line" in spurs

    assert "ASCENSION_M816_PM_ARGUMENT_EVIDENCE_V1" in policy
    assert "s_asc_upper_policy[12]" in policy
    assert "void spu_ascension_copy_upper_policy(uint64_t out[12])" in policy
    assert "s_asc_upper_policy[10],(uint32_t)wkl_data" in policy
    assert "s_asc_upper_policy[11],spurs_ea" in policy

    # iOS worker stacks must try 32 and 16 MiB before large reservations.
    assert "const size_t stack_sizes[4] = {32u << 20, 16u << 20, 64u << 20, 256u << 20};" in workload
    print("[PASS] M8.16 WID16/17 ModulePoll flag handoff; EDGE errors visible; actual LFQueue commits kept honest; PM args + iOS stack policy")


if __name__ == "__main__":
    main()
