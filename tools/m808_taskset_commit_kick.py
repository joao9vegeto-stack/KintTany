#!/usr/bin/env python3
"""M8.08: rescan SPURS tasksets when their reservation line is committed."""
from __future__ import annotations
import argparse
from pathlib import Path

MARKER = "ASCENSION_M808_TASKSET_COMMIT_KICK_V1"

def body_span(source: str, signature: str) -> tuple[int, int]:
    assert source.count(signature) == 1, f"missing or repeated {signature}"
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
    raise RuntimeError("unbalanced C block")

def apply(upstream: Path) -> None:
    path = upstream / "runtime/spu/spu_workload.c"
    s = path.read_text(errors="replace")
    if MARKER in s:
        for needle in ("spu_taskset_bits_committed(line);",
                       "void spu_taskset_bits_committed(uint32_t line)",
                       "spu_workload_copy_ascension_commit_metrics"):
            assert needle in s, f"partial M8.08: {needle}"
        return
    for needle in ("ASCENSION_M801_TASKSET_LOCKLINE_RMW_V1",
                   "ASCENSION_M801_TASKSET_RUNTIME_METRICS_V1",
                   "ts_bits_clear(taskset_ea + 0x20 + t / 8, m)"):
        assert needle in s, f"install M8.01 before M8.08: {needle}"
    signature = "static void spu_taskset_task_exited(uint32_t taskset_ea, uint32_t done_task)"
    a, b = body_span(s, signature)
    old = s[a:b]
    anchor = "    for (uint32_t t = 0; t < 128 && run; t++) {"
    assert old.count(anchor) == 1
    start = old.index(anchor)
    depth = 0
    end = None
    for i in range(old.index("{", start), len(old)):
        if old[i] == "{":
            depth += 1
        elif old[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end is not None
    loop = old[start:end]
    for needle in ("spu_workload_dispatch_async(vm_base + elf",
                   "asc_taskset_add(2, 1)", "asc_taskset_add(5, 1)"):
        assert needle in loop, f"missing production scheduler behavior {needle}"
    assert loop.count("done_task") == 1
    loop = loop.replace("done_task", "after_task")
    helper = """/* ASCENSION_M808_TASKSET_COMMIT_KICK_V1
 * Shared ready scan, always under ts_lock. Guest bitset modifications
 * remain protected by M8.01 lock-line operations. */
static void spu_taskset_start_ready_from_commit(uint32_t taskset_ea,
                                                uint8_t* run, int after_task)
{
    extern uint8_t* vm_base;
    extern uint32_t g_ydkj_real_taskset_ea, g_ydkj_real_taskid;
    uint8_t* ts = vm_base + taskset_ea;
""" + loop + "\n}\n"
    rewritten = old[:start] + "    spu_taskset_start_ready_from_commit(taskset_ea, run, (int)done_task);" + old[end:]
    for declaration in ("    extern uint8_t* vm_base;\n",
                        "    extern uint32_t g_ydkj_real_taskset_ea, g_ydkj_real_taskid;\n",
                        "    uint8_t* ts = vm_base + taskset_ea;\n"):
        rewritten = rewritten.replace(declaration, "", 1)
    assert "ts[" not in rewritten and "vm_base" not in rewritten
    metrics = """static uint64_t s_asc_taskset_commit_metrics[2];
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
    s = s[:a] + metrics + "\n" + helper + "\n" + rewritten + s[b:]
    callback = """/* A successful SPU PUTLLC/PUTLLUC may enable a task before any
 * existing runner exits. Trigger its real task scheduler immediately. */
void spu_taskset_bits_committed(uint32_t line)
{
    if (line & 127u) return;
    __atomic_add_fetch(&s_asc_taskset_commit_metrics[0], 1, __ATOMIC_RELAXED);
    ts_lock();
    for (int i = 0; i < TS_TRACK; i++) {
        uint32_t ea = s_ts_run[i].ea;
        if (!ea || (ea & ~127u) != line) continue;
        __atomic_add_fetch(&s_asc_taskset_commit_metrics[1], 1, __ATOMIC_RELAXED);
        spu_taskset_start_ready_from_commit(ea, s_ts_run[i].running, -1);
    }
    ts_unlock();
}
"""
    anchor2 = "static void spu_async_run(spu_async_job* j)"
    assert s.count(anchor2) == 1
    s = s.replace(anchor2, callback + "\n" + anchor2, 1)
    hook = "void spu_taskset_line_committed(uint32_t line)\n{\n"
    assert s.count(hook) == 1
    s = s.replace(hook, hook + "    spu_taskset_bits_committed(line);\n", 1)
    assert s.count(MARKER) == 1
    path.write_text(s)
    print("M8.08 WWS atomic-line commit -> tracked taskset scheduling ACTIVE")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--upstream", type=Path, required=True)
    apply(p.parse_args().upstream.resolve())

if __name__ == "__main__":
    main()
