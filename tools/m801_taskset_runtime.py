#!/usr/bin/env python3
"""M8.01 taskset lock-line correctness and WWS activity telemetry."""
from __future__ import annotations

import pathlib


LOCK_MARKER = "ASCENSION_M801_TASKSET_LOCKLINE_RMW_V1"
METRICS_MARKER = "ASCENSION_M801_TASKSET_RUNTIME_METRICS_V1"
METRIC_COUNT = 14


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"M8.01 expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def apply(upstream: pathlib.Path) -> None:
    taskset_path = upstream / "libs/spurs/spurs_taskset.h"
    taskset = taskset_path.read_text(errors="replace")
    if LOCK_MARKER not in taskset:
        old = '''static inline void spurs_bitset_set(uint32_t bitset_ea, uint32_t taskId)
{
    uint32_t word_ea = bitset_ea + (taskId / 32) * 4;
    uint32_t mask = (1u << 31) >> (taskId % 32);
    vm_write32(word_ea, vm_read32(word_ea) | mask);
}
static inline void spurs_bitset_clear(uint32_t bitset_ea, uint32_t taskId)
{
    uint32_t word_ea = bitset_ea + (taskId / 32) * 4;
    uint32_t mask = (1u << 31) >> (taskId % 32);
    vm_write32(word_ea, vm_read32(word_ea) & ~mask);
}
'''
        new = '''/* ASCENSION_M801_TASKSET_LOCKLINE_RMW_V1
 * Taskset bitsets share a 128-byte line updated by the SPU task library with
 * GETLLAR/PUTLLC. Serialize each PPU read-modify-write with that reservation
 * transaction or clearing one signalled task can erase a concurrent signal. */
static inline void spurs_bitset_rmw(uint32_t bitset_ea, uint32_t taskId, int set)
{
    uint32_t word_ea = bitset_ea + (taskId / 32) * 4;
    uint32_t mask = (1u << 31) >> (taskId % 32);
    spu_lockline_lock();
    uint8_t* p = vm_ptr8(word_ea);
    uint32_t v = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
                 ((uint32_t)p[2] << 8) | p[3];
    v = set ? (v | mask) : (v & ~mask);
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
    if (spu_coh_is_reserved(word_ea)) spu_coh_notify_write(word_ea);
    spu_lockline_unlock();
}
static inline void spurs_bitset_set(uint32_t bitset_ea, uint32_t taskId)
{
    spurs_bitset_rmw(bitset_ea, taskId, 1);
}
static inline void spurs_bitset_clear(uint32_t bitset_ea, uint32_t taskId)
{
    spurs_bitset_rmw(bitset_ea, taskId, 0);
}
'''
        taskset = replace_once(taskset, old, new, "SPURS bitset read-modify-write")
        taskset_path.write_text(taskset)
    elif "spurs_bitset_rmw(uint32_t bitset_ea, uint32_t taskId, int set)" not in taskset:
        raise SystemExit("partial M8.01 taskset bitset lock-line patch")

    workload_path = upstream / "runtime/spu/spu_workload.c"
    workload = workload_path.read_text(errors="replace")
    if LOCK_MARKER not in workload:
        include_anchor = '#include "spu_workload.h"\n'
        if '#include "spu_coherency.h"' not in workload:
            workload = replace_once(workload, include_anchor,
                                    include_anchor + '#include "spu_coherency.h"\n',
                                    "SPU coherency include")
        unlock = "static void ts_unlock(void) { InterlockedExchange(&s_ts_lock, 0); }\n"
        helper = unlock + '''
/* ASCENSION_M801_TASKSET_LOCKLINE_RMW_V1
 * Taskset ready/pending/enabled bytes share the line the SPU task library
 * changes with GETLLAR/PUTLLC. Keep scheduler clears in that same lock-line
 * transaction so an SPU-created task cannot be lost to a stale byte write. */
static void ts_bits_clear(uint32_t ea, uint8_t mask)
{
    extern uint8_t* vm_base;
    spu_lockline_lock();
    vm_base[ea] &= (uint8_t)~mask;
    if (spu_coh_is_reserved(ea)) spu_coh_notify_write(ea);
    spu_lockline_unlock();
}
'''
        workload = replace_once(workload, unlock, helper, "taskset lock helper")
        for old, new, label in (
            ("        ts[0x20 + t / 8] &= (uint8_t)~m;                 /* pending -> started */",
             "        ts_bits_clear(taskset_ea + 0x20 + t / 8, m);       /* pending -> started */",
             "pending-to-started clear"),
            ("        ts[0x10 + done_task / 8] &= (uint8_t)~m;",
             "        ts_bits_clear(taskset_ea + 0x10 + done_task / 8, m);",
             "ready clear"),
            ("        ts[0x20 + done_task / 8] &= (uint8_t)~m;",
             "        ts_bits_clear(taskset_ea + 0x20 + done_task / 8, m);",
             "pending clear"),
            ("        ts[0x30 + done_task / 8] &= (uint8_t)~m;",
             "        ts_bits_clear(taskset_ea + 0x30 + done_task / 8, m);",
             "enabled clear"),
        ):
            workload = replace_once(workload, old, new, label)
        unused_taskset_base = '''    extern uint8_t* vm_base;
    ts_lock();
    uint8_t* ts = vm_base + taskset_ea;
    uint8_t* run = ts_running(taskset_ea);'''
        cleaned_task_exit = '''    ts_lock();
    uint8_t* run = ts_running(taskset_ea);'''
        workload = replace_once(workload, unused_taskset_base, cleaned_task_exit,
                                "obsolete taskset base pointer")
        workload_path.write_text(workload)
    elif "static void ts_bits_clear(uint32_t ea, uint8_t mask)" not in workload:
        raise SystemExit("partial M8.01 taskset scheduler lock-line patch")

    workload = workload_path.read_text(errors="replace")
    if METRICS_MARKER not in workload:
        metrics = '''/* ASCENSION_M801_TASKSET_RUNTIME_METRICS_V1
 * Direct taskset counters; the generic job-chain API is measured separately. */
static uint64_t s_asc_taskset_metrics[14];
static void asc_taskset_add(unsigned slot, uint64_t value)
{
    __atomic_add_fetch(&s_asc_taskset_metrics[slot], value, __ATOMIC_RELAXED);
}
static void asc_taskset_store(unsigned slot, uint64_t value)
{
    __atomic_store_n(&s_asc_taskset_metrics[slot], value, __ATOMIC_RELAXED);
}
void spu_workload_reset_ascension_taskset_metrics(void)
{
    for (unsigned i = 0; i < 14; ++i)
        __atomic_store_n(&s_asc_taskset_metrics[i], 0, __ATOMIC_RELAXED);
}
void spu_workload_copy_ascension_taskset_metrics(uint64_t out[14])
{
    if (!out) return;
    for (unsigned i = 0; i < 14; ++i)
        out[i] = __atomic_load_n(&s_asc_taskset_metrics[i], __ATOMIC_RELAXED);
}
'''
        metrics_anchor = "int g_cri_video_dma = 0;\n"
        workload = replace_once(workload, metrics_anchor,
                                metrics_anchor + "\n" + metrics,
                                "taskset metrics API")

        track = '''void spu_taskset_track(uint32_t taskset_ea)
{
    if (!taskset_ea) return;'''
        workload = replace_once(workload, track,
                                track + "\n    asc_taskset_add(0, 1);",
                                "taskset registration metric")
        exited = '''static void spu_taskset_task_exited(uint32_t taskset_ea, uint32_t done_task)
{
    spu_taskset_task_ended();'''
        workload = replace_once(workload, exited, exited + '''
    asc_taskset_add(1, 1);
    asc_taskset_store(12, taskset_ea);
    asc_taskset_store(13, done_task);''', "taskset exit metric")
        candidate = '''        if (!((ts[0x10 + t / 8] | ts[0x20 + t / 8]) & m)) continue;
        const uint8_t* ti = ts + 0x80 + 0x30 * t;'''
        workload = replace_once(workload, candidate, '''        if (!((ts[0x10 + t / 8] | ts[0x20 + t / 8]) & m)) continue;
        asc_taskset_add(2, 1);
        const uint8_t* ti = ts + 0x80 + 0x30 * t;''',
                              "ready task candidate metric")
        valid_elf = '''        if (!sz) continue;
        ts_bits_clear(taskset_ea + 0x20 + t / 8, m);       /* pending -> started */'''
        workload = replace_once(workload, valid_elf, '''        if (!sz) continue;
        asc_taskset_add(3, 1);
        ts_bits_clear(taskset_ea + 0x20 + t / 8, m);       /* pending -> started */''',
                              "valid task ELF metric")
        dispatch = '''        if (!spu_workload_dispatch_async(vm_base + elf, (uint32_t)sz, ctx))
            run[t / 8] &= (uint8_t)~m;'''
        workload = replace_once(workload, dispatch, '''        asc_taskset_add(4, 1);
        if (!spu_workload_dispatch_async(vm_base + elf, (uint32_t)sz, ctx)) {
            asc_taskset_add(6, 1);
            run[t / 8] &= (uint8_t)~m;
        } else {
            asc_taskset_add(5, 1);
            asc_taskset_store(12, taskset_ea);
            asc_taskset_store(13, t);
        }''', "taskset scheduler dispatch result")

        async_entry = '''static void spu_async_run(spu_async_job* j)
{
    spu_taskset_mark(j->taskset_ea, j->taskid, 1);'''
        workload = replace_once(workload, async_entry, '''static void spu_async_run(spu_async_job* j)
{
    const uint32_t asc_taskset_ea = j->taskset_ea;
    int asc_load_seen = 0;
    if (asc_taskset_ea) {
        asc_taskset_add(7, 1);
        asc_taskset_add(11, 1);
        asc_taskset_store(12, asc_taskset_ea);
        asc_taskset_store(13, j->taskid);
    }
    spu_taskset_mark(j->taskset_ea, j->taskid, 1);''',
                              "async task entry metric")
        load = '''        int loaded = (ts_slot && ts_slot->loaded)
                   ? 1
                   : (did_load = 1, spu_elf_load_to_ls(j->image, j->image_size, ls, &entry));
        if (ts_slot && did_load && loaded) ts_slot->loaded = 1;'''
        workload = replace_once(workload, load, load + '''
        if (asc_taskset_ea) {
            asc_taskset_add(loaded ? 8 : 9, 1);
            asc_load_seen = 1;
        }''', "async task ELF load metric")
        tail = '''    if (ts_slot) {
#ifdef _WIN32
        ReleaseSRWLockExclusive(&ts_slot->lock);
#else
        pthread_mutex_unlock(&ts_slot->lock);
#endif
    }
    free(j);'''
        workload = replace_once(workload, tail, '''    if (ts_slot) {
#ifdef _WIN32
        ReleaseSRWLockExclusive(&ts_slot->lock);
#else
        pthread_mutex_unlock(&ts_slot->lock);
#endif
    }
    if (asc_taskset_ea) {
        if (!asc_load_seen) asc_taskset_add(9, 1);
        asc_taskset_add(10, 1);
        __atomic_sub_fetch(&s_asc_taskset_metrics[11], 1, __ATOMIC_RELAXED);
    }
    free(j);''', "async task runner return metric")
        workload_path.write_text(workload)
    else:
        required = ("spu_workload_reset_ascension_taskset_metrics",
                    "spu_workload_copy_ascension_taskset_metrics",
                    "asc_taskset_add(7, 1)", "asc_taskset_add(10, 1)")
        missing = [needle for needle in required if needle not in workload]
        if missing:
            raise SystemExit(f"partial M8.01 taskset metrics patch: {missing}")
