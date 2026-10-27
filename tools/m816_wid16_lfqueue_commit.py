#!/usr/bin/env python3
"""M8.16: preserve SPURS workload flags through ModulePoll and report real EDGE handoff."""
from pathlib import Path
import argparse

MARK = "ASCENSION_M816_WID16_FLAG_EDGE_HANDOFF_V1"
POLICY_MARK = "ASCENSION_M816_PM_ARGUMENT_EVIDENCE_V1"


def once(source: str, old: str, new: str, label: str) -> str:
    n = source.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected one anchor, found {n}: {old[:100]!r}")
    return source.replace(old, new, 1)


def patch_cellspurs(root: Path) -> None:
    path = root / "libs/spurs/cellSpurs.c"
    source = path.read_text(errors="replace")
    if MARK in source:
        required = (
            "static volatile u64 s_asc_edge_metrics[6]",
            "out[6]",
            "edge_event_rc == CELL_OK",
            "s_asc_edge_metrics[5]",
            "ASCENSION_M811_EDGE_CLASSIFICATION_V1",
        )
        missing = [x for x in required if x not in source]
        if missing:
            raise SystemExit(f"partial M8.16 EDGE handoff patch: {missing}")
        return

    if "ASCENSION_M811_EDGE_CLASSIFICATION_V1" not in source:
        raise SystemExit("M8.16 requires M8.11 EDGE completion instrumentation")
    if "ASCENSION_M810_NATIVE_LFQUEUE_V1" not in source:
        raise SystemExit("M8.16 requires the native LFQueue implementation")

    # EDGE zlib is a synchronous fast path, not a ring-buffer commit. Count
    # completion-event delivery separately from real LFQueue push commits.
    source = once(
        source,
        "static volatile u64 s_asc_edge_metrics[5];",
        f"/* {MARK}: count only successful guest event-flag handoffs. */\n"
        "static volatile u64 s_asc_edge_metrics[6];",
        "EDGE metric declaration",
    )
    if source.count("for(unsigned k=0;k<5;k++)") != 2:
        raise SystemExit("M8.16 expected reset/copy loops for the five old EDGE counters")
    source = source.replace("for(unsigned k=0;k<5;k++)",
                            "for(unsigned k=0;k<6;k++)")
    source = once(
        source,
        "void cellSpursCopyAscensionEdgeMetrics(u64 out[5])",
        "void cellSpursCopyAscensionEdgeMetrics(u64 out[6])",
        "EDGE metrics copy API",
    )
    old = """          if (left == 1u && flag && bits) {
              cellSpursEventFlagSet((CellSpursEventFlag*)(uintptr_t)flag, bits);
              __atomic_fetch_add(&s_asc_edge_metrics[4],1,__ATOMIC_RELAXED);
          }"""
    new = """          if (left == 1u && flag && bits) {
              const s32 edge_event_rc =
                  cellSpursEventFlagSet((CellSpursEventFlag*)(uintptr_t)flag, bits);
              if (edge_event_rc == CELL_OK) {
                  __atomic_fetch_add(&s_asc_edge_metrics[4],1,__ATOMIC_RELAXED);
              } else {
                  __atomic_fetch_add(&s_asc_edge_metrics[5],1,__ATOMIC_RELAXED);
                  fprintf(stderr,
                          "[cellSpurs] EDGE completion flag failed rc=0x%08X event=0x%08X bits=0x%04X\\n",
                          (unsigned)edge_event_rc, flag, (unsigned)bits);
                  return edge_event_rc;
              }
          }"""
    source = once(source, old, new, "EDGE event flag completion")
    # Keep the production selector and admission on the same non-consuming
    # lookup protocol. The flag is consumed only when ModulePoll selects it.
    selector_start = source.find("u32 spurs_poll_select(u32 ea, u32 current, u32 spu)")
    if selector_start < 0:
        raise SystemExit("M8.16 cannot find the native SPURS selector")
    selector_end = source.find("\n}", selector_start)
    selector = source[selector_start:selector_end + 2]
    for token in ("spurs_workload_flag_peek(ea, wid)",
                  "spurs_workload_flag_take(ea, wid)"):
        if token not in selector:
            raise SystemExit("M8.16 selector lacks flag handoff token: " + token)
    scheduler_start = source.find("static DWORD WINAPI spurs_kernel_thread(LPVOID p)\n{")
    scheduler_end = source.find("\nstatic s32 spurs_scheduler_start", scheduler_start)
    if scheduler_start < 0 or scheduler_end < 0:
        raise SystemExit("M8.16 cannot find native SPURS admission code")
    scheduler = source[scheduler_start:scheduler_end]
    if "const int flagged = spurs_workload_flag_peek(ea, wid);" not in scheduler:
        raise SystemExit("M8.16 admission must peek, not consume, WWS workload flags")
    if "const int flagged = spurs_workload_flag_take(ea, wid);" in scheduler:
        raise SystemExit("M8.16 admission still consumes a workload flag before ModulePoll")
    path.write_text(source)


def patch_policy_arguments(root: Path) -> None:
    path = root / "runtime/spu/spurs_policy.c"
    source = path.read_text(errors="replace")
    if POLICY_MARK in source:
        required = ("s_asc_upper_policy[12]", "out[12]",
                    "s_asc_upper_policy[10],(uint32_t)wkl_data",
                    "s_asc_upper_policy[11],spurs_ea")
        missing = [x for x in required if x not in source]
        if missing:
            raise SystemExit(f"partial M8.16 PM argument evidence: {missing}")
        return
    if "ASCENSION_M812_SPURS2_POLICY_32_V1" not in source:
        raise SystemExit("M8.16 requires the M8.12 native upper-WID policy patch")

    source = once(
        source,
        "static volatile uint64_t s_asc_upper_policy[10];",
        f"/* {POLICY_MARK}: expose the exact native PM data/instance arguments. */\n"
        "static volatile uint64_t s_asc_upper_policy[12];",
        "PM metric storage",
    )
    source = once(source,
                  "for(unsigned i=0;i<10;i++)\n        __atomic_store_n(&s_asc_upper_policy[i],0,__ATOMIC_RELAXED);",
                  "for(unsigned i=0;i<12;i++)\n        __atomic_store_n(&s_asc_upper_policy[i],0,__ATOMIC_RELAXED);",
                  "PM reset counter length")
    source = once(source, "void spu_ascension_copy_upper_policy(uint64_t out[10])",
                  "void spu_ascension_copy_upper_policy(uint64_t out[12])",
                  "PM copy API length")
    source = once(source, "for(unsigned i=0;i<10;i++)\n        out[i]=__atomic_load_n(&s_asc_upper_policy[i],__ATOMIC_RELAXED);",
                  "for(unsigned i=0;i<12;i++)\n        out[i]=__atomic_load_n(&s_asc_upper_policy[i],__ATOMIC_RELAXED);",
                  "PM copy counter length")
    old = """        __atomic_store_n(&s_asc_upper_policy[9],spu_num,__ATOMIC_RELAXED);
    }"""
    new = """        __atomic_store_n(&s_asc_upper_policy[9],spu_num,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[10],(uint32_t)wkl_data,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[11],spurs_ea,__ATOMIC_RELAXED);
    }"""
    source = once(source, old, new, "PM argument evidence stores")
    path.write_text(source)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    root = args.upstream.resolve()
    patch_cellspurs(root)
    patch_policy_arguments(root)
    print("[PASS] M8.16 WID16 flag handoff, truthful EDGE event completion, PM argument telemetry")


if __name__ == "__main__":
    main()
