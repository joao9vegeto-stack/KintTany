#!/usr/bin/env python3
"""M8.08: schedule tracked SPURS tasksets after successful SPU atomic-line commits."""
from __future__ import annotations
import argparse
from pathlib import Path

MARKER = "ASCENSION_M808_TASKSET_COMMIT_KICK_V2"

def body_span(source: str, signature: str) -> tuple[int, int]:
    assert source.count(signature) == 1, f"expected exactly one {signature}"
    a = source.index(signature)
    opening = source.index("{", a + len(signature))
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return a, i + 1
    raise RuntimeError("unbalanced production C function")

def apply(upstream: Path) -> None:
    path = upstream / "runtime/spu/spu_workload.c"
    s = path.read_text(errors="replace")
    if MARKER in s:
        for needle in ("spu_taskset_bits_committed(line);",
                       "void spu_taskset_bits_committed(uint32_t line)",
                       "spu_workload_copy_ascension_commit_metrics"):
            assert needle in s, f"partial M8.08: {needle}"
        return

    # Patch 0019 *already* extracts the actual production scheduler from the
    # exit path into ts_start_ready(). Never extract it a second time.
    for needle in ("ASCENSION_M801_TASKSET_LOCKLINE_RMW_V1",
                   "ASCENSION_M801_TASKSET_RUNTIME_METRICS_V1",
                   "static void ts_start_ready(uint32_t taskset_ea, uint32_t done_task)",
                   "ts_start_ready(taskset_ea, done_task);",
                   "ts_bits_clear(taskset_ea + 0x20 + t / 8, m)",
                   "asc_taskset_add(5, 1)"):
        assert needle in s, f"M8.08 requires full M8.01+patch0019: {needle}"

    metrics = """/* ASCENSION_M808_TASKSET_COMMIT_KICK_V2 */
static uint64_t s_asc_taskset_commit_metrics[2];
void spu_workload_reset_ascension_commit_metrics(void)
{
    __atomic_store_n(&s_asc_taskset_commit_metrics[0], 0, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_taskset_commit_metrics[1], 0, __ATOMIC_RELAXED);
}
void spu_workload_copy_ascension_commit_metrics(uint64_t out[2])
{
    if (!out) return;
    out[0] = __atomic_load_n(&s_asc_taskset_commit_metrics[0], __ATOMIC_RELAXED);
    out[1] = __atomic_load_n(&s_asc_taskset_commit_metrics[1], __ATOMIC_RELAXED);
}
"""
    anchor = "static void ts_start_ready(uint32_t taskset_ea, uint32_t done_task)"
    assert s.count(anchor) == 1
    s = s.replace(anchor, metrics + "\n" + anchor, 1)

    # channels.c notifies this callback *after* the MFC reservation-line
    # lock is released, on both PUTLLC and PUTLLUC; the existing WAIT_SIGNAL
    # wakeup in this callback must be preserved.
    callback = """/* Successful SPU GETLLAR/PUTLLC can create the next task in a
 * taskset even when every previously dispatched worker is still alive.
 * Patch 0019 already defines ts_start_ready(), including run bitguards,
 * guest TaskInfo decoding, real ELF checks, and M8.01 counters. */
void spu_taskset_bits_committed(uint32_t line)
{
    static uint64_t s_commit_scan_tick;
    if (line & 127u) return;
    __atomic_add_fetch(&s_asc_taskset_commit_metrics[0], 1, __ATOMIC_RELAXED);
    const uint64_t tick = __atomic_add_fetch(&s_commit_scan_tick, 1, __ATOMIC_RELAXED);
    ts_lock();
    for (int i = 0; i < TS_TRACK; i++) {
        uint32_t taskset_ea = s_ts_run[i].ea;
        if (!taskset_ea) continue;
        if ((taskset_ea & ~127u) == line)
            __atomic_add_fetch(&s_asc_taskset_commit_metrics[1], 1, __ATOMIC_RELAXED);
        /* Immediate scan for the taskset whose reservation line committed. */
        if ((taskset_ea & ~127u) == line)
            ts_start_ready(taskset_ea, UINT32_MAX);
        /* Defensive rescan: guest Taskset2 may publish its task descriptor
         * and ready bits through different translated atomic paths. Poll all
         * tracked tasksets every 64 commits so a missed/aliased line callback
         * cannot strand a ready task forever. The real scanner still checks
         * ready/pending/enabled bits, ELF bounds, and running guards. */
        if ((tick & 63u) == 0)
            ts_start_ready(taskset_ea, UINT32_MAX);
    }
    ts_unlock();
}
"""
    before = "static void spu_async_run(spu_async_job* j)"
    assert s.count(before) == 1
    s = s.replace(before, callback + "\n" + before, 1)
    hook = "void spu_taskset_line_committed(uint32_t line)\n{\n"
    assert s.count(hook) == 1, "missing MFC line-commit hook"
    s = s.replace(hook, hook + "    spu_taskset_bits_committed(line);\n", 1)
    assert s.count(MARKER) == 1
    path.write_text(s)
    print("M8.08: SPU atomic commit now runs the existing, metrics-bearing WWS task scheduler")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--upstream", type=Path, required=True)
    apply(p.parse_args().upstream.resolve())

if __name__ == "__main__":
    main()
