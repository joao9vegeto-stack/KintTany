#!/usr/bin/env python3
"""Apply the game-proven SPURS2/task scheduling path to the pinned runtime.

The PPU lift calls SPURS v2 entry points that the pinned PS3Recomp runtime did
not provide. The bundled upstream patches come from the public Ascension PC
port's PS3Recomp work; this adds the task APIs used by its later milestones and
an optional host Edge Zlib path for Ascension's streaming asset queue.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

from m801_taskset_runtime import LOCK_MARKER as TASKSET_LOCK_MARKER
from m801_taskset_runtime import METRICS_MARKER as TASKSET_METRICS_MARKER
from m801_taskset_runtime import apply as apply_m801_taskset_runtime


PIN = "39a36296511c445707adabcd312f0b740cfbd694"
MARKER = "ASCENSION_M772_SPURS2_TASK_API_V2"
WORKLOADS_MARKER = "ASCENSION_M772_SPURS2_WORKLOADS_32_V1"
LFQUEUE_MARKER = "ASCENSION_M772_LFQUEUE_SDK_LAYOUT_V1"
PM_DIAGNOSTICS_MARKER = "ASCENSION_M785_SPURS_PM_DIAGNOSTICS_V1"
ASCENSION_POLICY_MARKER = "ASCENSION_M786_WWS_TEMPA_READY_LEVEL_V1"
JOB_METRICS_MARKER = "ASCENSION_M787_SPURS_JOB_METRICS_V1"
PM_CAPTURE_MARKER = "ASCENSION_M788_CAPTURE_REQUESTED_PM_V1"
DYNAMIC_WWS_PM_MARKER = "ASCENSION_M790_DYNAMIC_WWS_PM_ROLE_V1"
LWCOND_SEMANTICS_MARKER = "ASCENSION_M791_LWCOND_SIGNAL_WAIT_V1"
REPORT_HOLD_MARKER = "ASCENSION_M798_GCM_REPORT_SPU_HOLD_V1"
PARK_SPU_HOLD_MARKER = "ASCENSION_M803_GCM_PARK_SPU_HOLD_V1"
SPURS_REPORT_WAKE_MARKER = "ASCENSION_M804_SPURS_REPORT_WAKE_V1"
STACK_METRICS_MARKER = "ASCENSION_M804_SPU_STACK_RECOVERY_V1"
TASK_ACTIVITY_MARKER = "ASCENSION_M798_SPURS_TASK_ACTIVITY_V1"
WORKLOAD_FLAG_MARKER = "ASCENSION_M799_SPURS_WORKLOAD_FLAG_V1"
TASKSET_WID_MARKER = "ASCENSION_M800_TASKSET_CURRENT_WORKLOAD_V1"


def run(argv: list[str], *, capture: bool = False) -> str:
    p = subprocess.run(argv, check=False, text=True, capture_output=capture)
    if p.returncode:
        detail = p.stderr if capture else ""
        raise SystemExit(f"command failed ({p.returncode}): {argv!r}\n{detail}")
    return p.stdout if capture else ""


def apply_patch(upstream: pathlib.Path, patch: pathlib.Path,
                markers: tuple[tuple[pathlib.Path, str], ...], *, zero_context: bool = False) -> None:
    if all(marker in path.read_text(errors="replace") for path, marker in markers):
        return
    if any(marker in path.read_text(errors="replace") for path, marker in markers):
        raise SystemExit(f"partial application detected for {patch.name}; refusing a mixed runtime")
    flags = ["--unidiff-zero"] if zero_context else []
    run(["git", "-C", str(upstream), "apply", *flags, "--check", str(patch)])
    run(["git", "-C", str(upstream), "apply", *flags, str(patch)])


def apply_api_layer(upstream: pathlib.Path, repo: pathlib.Path) -> None:
    c = upstream / "libs/spurs/cellSpurs.c"
    h = upstream / "libs/spurs/cellSpurs.h"
    source = c.read_text(errors="replace")
    header = h.read_text(errors="replace")
    if MARKER in source and MARKER in header:
        return
    if MARKER in source or MARKER in header:
        raise SystemExit("partial SPURS2 API layer detected")

    task_apis = r'''/* ASCENSION_M772_SPURS2_TASK_API_V1
 * Second-generation task attributes used by GoW Ascension. Layout fields are
 * big-endian guest words; keep them in VM memory, not host structs. */
s32 _cellSpursTaskAttribute2Initialize(void* attr, u32 revision)
{
    const u32 ea = (u32)(uintptr_t)attr;
    if (!ea) return CELL_SPURS_TASK_ERROR_NULL_POINTER;
    if (!spurs_guest_range_valid(ea, 0x24)) return CELL_SPURS_TASK_ERROR_FAULT;
    vm_write32(ea, revision);
    for (u32 off = 0x04; off < 0x24; off += 4) vm_write32(ea + off, 0);
    return CELL_OK;
}

s32 cellSpursCreateTask2(CellSpursTaskset* taskset, CellSpursTaskId* taskId,
                         void* elf, u32 argument_ea, u32 attr_ea)
{
    u32 context_ea = 0, size_context = 0, ls_pattern_ea = 0;
    if (attr_ea) {
        if (!spurs_guest_range_valid(attr_ea, 0x24))
            return CELL_SPURS_TASK_ERROR_FAULT;
        size_context = vm_read32(attr_ea + 0x04);
        context_ea = (u32)vm_read64(attr_ea + 0x08);
        ls_pattern_ea = attr_ea + 0x10;
    }
    return cellSpursCreateTask(taskset, taskId, elf,
                               (void*)(uintptr_t)context_ea,
                               size_context, ls_pattern_ea, argument_ea);
}

'''
    anchor_task = "/* Create a task from a pre-initialized attribute (carries ELF EA + context)."
    if source.count(anchor_task) != 1:
        raise SystemExit("SPURS2 patch cannot find the CreateTaskWithAttribute insertion point")
    source = source.replace(anchor_task, task_apis + anchor_task, 1)

    taskset_apis = r'''/* ASCENSION_M772_SPURS2_TASK_API_V1 */
s32 cellSpursDestroyTaskset2(CellSpursTaskset* taskset)
{
    return cellSpursDestroyTaskset(taskset);
}

s32 cellSpursTasksetGetSpursAddress(const CellSpursTaskset* taskset, u32* spurs_out)
{
    const u32 ts = (u32)(uintptr_t)taskset;
    const u32 out = (u32)(uintptr_t)spurs_out;
    if (!ts || !out) return CELL_SPURS_TASK_ERROR_NULL_POINTER;
    if (!spurs_guest_range_valid(ts + CSTS_SPURS, 8) ||
        !spurs_guest_range_valid(out, 4)) return CELL_SPURS_TASK_ERROR_FAULT;
    vm_write32(out, (u32)vm_read64(ts + CSTS_SPURS));
    return CELL_OK;
}

'''
    anchor_taskset = "s32 cellSpursShutdownTaskset(CellSpursTaskset* taskset)"
    if source.count(anchor_taskset) != 1:
        raise SystemExit("SPURS2 patch cannot find the Taskset2 insertion point")
    source = source.replace(anchor_taskset, taskset_apis + anchor_taskset, 1)

    join_apis = r'''/* ASCENSION_M772_SPURS2_TASK_API_V1 */
static s32 spurs_task2_write_exit_code(u32 exit_code_ea)
{
    if (!exit_code_ea) return CELL_OK;
    if (!spurs_guest_range_valid(exit_code_ea, 4)) return CELL_SPURS_TASK_ERROR_FAULT;
    vm_write32(exit_code_ea, 0); /* SPU task exit codes are not tracked yet. */
    return CELL_OK;
}

s32 cellSpursTryJoinTask2(CellSpursTaskset* taskset, CellSpursTaskId taskId,
                          s32* exitCode)
{
    const u32 ts = (u32)(uintptr_t)taskset;
    const u32 ec = (u32)(uintptr_t)exitCode;
    if (!ts) return CELL_SPURS_TASK_ERROR_NULL_POINTER;
    if (taskId >= CELL_SPURS_MAX_TASK) return CELL_SPURS_TASK_ERROR_INVAL;
    const u32 byte_ea = ts + 0x30 + taskId / 8;
    if (!spurs_guest_range_valid(byte_ea, 1)) return CELL_SPURS_TASK_ERROR_FAULT;
    if (vm_read8(byte_ea) & (u8)(0x80u >> (taskId % 8)))
        return CELL_SPURS_TASK_ERROR_BUSY;
    return spurs_task2_write_exit_code(ec);
}

s32 cellSpursJoinTask2(CellSpursTaskset* taskset, CellSpursTaskId taskId,
                       s32* exitCode)
{
    const u32 ts = (u32)(uintptr_t)taskset;
    const u32 ec = (u32)(uintptr_t)exitCode;
    if (!ts) return CELL_SPURS_TASK_ERROR_NULL_POINTER;
    if (taskId >= CELL_SPURS_MAX_TASK) return CELL_SPURS_TASK_ERROR_INVAL;
    const u32 byte_ea = ts + 0x30 + taskId / 8;
    if (!spurs_guest_range_valid(byte_ea, 1)) return CELL_SPURS_TASK_ERROR_FAULT;
    for (u32 waited_ms = 0; waited_ms < 20000; ++waited_ms) {
        if (!(vm_read8(byte_ea) & (u8)(0x80u >> (taskId % 8))))
            return spurs_task2_write_exit_code(ec);
#ifdef _WIN32
        Sleep(1);
#else
        const struct timespec delay = {0, 1000000};
        nanosleep(&delay, NULL);
#endif
    }
    fprintf(stderr, "[cellSpurs] JoinTask2 timeout: taskset=0x%08X id=%u still enabled\n",
            ts, taskId);
    return CELL_SPURS_TASK_ERROR_SRCH;
}

'''
    anchor_join = "s32 cellSpursSendSignal(CellSpursTaskset* taskset, CellSpursTaskId taskId)"
    if source.count(anchor_join) != 1:
        raise SystemExit("SPURS2 patch cannot find the JoinTask2 insertion point")
    source = source.replace(anchor_join, join_apis + anchor_join, 1)

    workload_flag_apis = r'''/* ASCENSION_M772_SPURS2_TASK_API_V2 */
static int spurs_guest_range_valid(u32 ea, u32 bytes);

/* WorkloadFlag lives in the guest CellSpurs cache line at +0x60. Return its
 * guest EA, never a host pointer, so the lifted PPU can use its normal guest
 * atomic operations on the same bytes as the SPU policy module. */
s32 cellSpursGetWorkloadFlag(CellSpurs* spurs, u32* flag_ea_out)
{
    const u32 spurs_ea = (u32)(uintptr_t)spurs;
    const u32 out_ea = (u32)(uintptr_t)flag_ea_out;
    if (!spurs_ea || !out_ea) return CELL_SPURS_CORE_ERROR_NULL_POINTER;
    if (spurs_ea & 0x7Fu) return CELL_SPURS_CORE_ERROR_ALIGN;
    if (!spurs_guest_range_valid(spurs_ea + SPURS_WKL_FLAG, 8) ||
        !spurs_guest_range_valid(out_ea, 4)) return CELL_SPURS_TASK_ERROR_FAULT;
    vm_write32(out_ea, spurs_ea + SPURS_WKL_FLAG);
    return CELL_OK;
}

/* Match RPCS3's receiver ownership rules at guest offsets +0x6C/+0x77. The
 * flag word and receiver byte share a reservation line with the SPU kernel;
 * update them as one lock-line transaction and wake any reserving SPU. */
s32 _cellSpursWorkloadFlagReceiver(CellSpurs* spurs, u32 wid, u32 is_set)
{
    const u32 spurs_ea = (u32)(uintptr_t)spurs;
    if (!spurs_ea) return CELL_SPURS_CORE_ERROR_NULL_POINTER;
    if (spurs_ea & 0x7Fu) return CELL_SPURS_CORE_ERROR_ALIGN;
    if (wid >= CELL_SPURS_MAX_WORKLOAD) return CELL_SPURS_CORE_ERROR_INVAL;
    if (!spurs_guest_range_valid(spurs_ea, SPURS_INST_SIZE))
        return CELL_SPURS_TASK_ERROR_FAULT;
    if (!(vm_read32(spurs_ea + SPURS_WKL_ENABLED) & (0x80000000u >> wid)))
        return CELL_SPURS_CORE_ERROR_SRCH;

    spu_lockline_lock();
    const u32 receiver_ea = spurs_ea + SPURS_WKL_FLAG_RCV;
    const u8 receiver = vm_base[receiver_ea];
    s32 rc = CELL_OK;
    if (is_set && receiver != 0xFFu) rc = CELL_SPURS_CORE_ERROR_BUSY;
    else if (!is_set && receiver != (u8)wid) rc = CELL_SPURS_CORE_ERROR_PERM;
    else {
        /* The SDK resets the workload flag to all ones on every ownership
         * change; its receiver is the low byte of that BE flag structure. */
        vm_base[spurs_ea + SPURS_WKL_FLAG_VAL + 0] = 0xFFu;
        vm_base[spurs_ea + SPURS_WKL_FLAG_VAL + 1] = 0xFFu;
        vm_base[spurs_ea + SPURS_WKL_FLAG_VAL + 2] = 0xFFu;
        vm_base[spurs_ea + SPURS_WKL_FLAG_VAL + 3] = 0xFFu;
        vm_base[receiver_ea] = is_set ? (u8)wid : 0xFFu;
    }
    ef_line_end(spurs_ea);
    return rc;
}

'''
    anchor_workload_flag = "s32 cellSpursGetNumSpuThread(const CellSpurs* spurs, u32* nThreads)"
    if source.count(anchor_workload_flag) != 1:
        raise SystemExit("SPURS2 patch cannot find the workload-flag API insertion point")
    source = source.replace(anchor_workload_flag, workload_flag_apis + anchor_workload_flag, 1)

    # The reference taskset scheduler starts a job under its tracking lock. If
    # dispatch fails, clear that mark while still holding the lock so a failed
    # image lookup cannot masquerade as a running task forever.
    workload_source = (upstream / "runtime/spu/spu_workload.c").read_text(errors="replace")
    dispatch_anchor = "        spu_workload_dispatch_async(vm_base + elf, (uint32_t)sz, ctx);"
    if workload_source.count(dispatch_anchor) != 1:
        raise SystemExit("SPURS2 patch cannot find taskset async dispatch")
    workload_source = workload_source.replace(dispatch_anchor,
        "        if (!spu_workload_dispatch_async(vm_base + elf, (uint32_t)sz, ctx))\n"
        "            run[t / 8] &= (uint8_t)~m;", 1)

    # The Ascension taskset milestone allocates the two LV2 flags needed by
    # CellSpursTaskset2. Fail the HLE visibly if either allocation fails.
    event_block = '''        extern int64_t sys_event_flag_create_host(uint32_t, uint64_t);
        sys_event_flag_create_host(taskset_ea + CSTS_EVENT_FLAG_ID1, 0);
        sys_event_flag_create_host(taskset_ea + CSTS_EVENT_FLAG_ID2, 0);'''
    event_replacement = '''        extern int64_t sys_event_flag_create_host(uint32_t, uint64_t);
        const int64_t flag1_rc = sys_event_flag_create_host(taskset_ea + CSTS_EVENT_FLAG_ID1, 0);
        if (flag1_rc != CELL_OK) return (s32)flag1_rc;
        const int64_t flag2_rc = sys_event_flag_create_host(taskset_ea + CSTS_EVENT_FLAG_ID2, 0);
        if (flag2_rc != CELL_OK) return (s32)flag2_rc;'''
    if source.count(event_block) != 1:
        raise SystemExit("SPURS2 patch cannot find the Taskset2 event flag allocation")
    source = source.replace(event_block, event_replacement, 1)

    # The GoW2/Ascension PC port proved the producer side of this queue is
    # required to wake the first SPU worker. The 2nd-generation Edge Zlib
    # path decodes streamed WADs on the host and honours each request's skip.
    push_anchor = '''    if (!queue_ea || !data_ea) return CELL_SPURS_TASK_ERROR_NULL_POINTER;
    if (s_off) return CELL_OK;

    const uint32_t q = (uint32_t)queue_ea;'''
    edge_hle = r'''    if (!queue_ea || !data_ea) return CELL_SPURS_TASK_ERROR_NULL_POINTER;
    if (s_off) return CELL_OK;

    /* ASCENSION_M772_EDGE_ZLIB_HLE_V2: stream chunks from Edge Zlib on the
     * host. The queue element references a zlib request; +0x24 is the output
     * skip, so WAD header and payload reads can repeat one compressed stream. */
    { static int s_edge = -1;
      if (s_edge < 0) s_edge = getenv("PS3_EDGE_ZLIB_HLE") ? 1 : 0;
      if (s_edge) {
          const u32 e = (u32)data_ea;
          if (!spurs_guest_range_valid(e, 0x28)) return CELL_SPURS_TASK_ERROR_FAULT;
          const u32 src = vm_read32(e + 0x00), dst = vm_read32(e + 0x04);
          const u32 srclen = vm_read32(e + 0x08), cap = vm_read32(e + 0x0C);
          const u32 counter = vm_read32(e + 0x10) & ~3u;
          const u32 flag = vm_read32(e + 0x14);
          const u16 bits = (u16)(vm_read32(e + 0x18) >> 16);
          const u32 skip = vm_read32(e + 0x24);
          if (!src || !dst || !counter || !srclen || srclen >= 0x01000000u ||
              !cap || cap > 0x01000000u || skip >= 0x01000000u ||
              !spurs_guest_range_valid(src, srclen) ||
              !spurs_guest_range_valid(dst, cap) ||
              !spurs_guest_range_valid(counter, 4))
              return CELL_SPURS_TASK_ERROR_FAULT;
          extern int edge_inflate(uint8_t*, uint32_t, const uint8_t*, uint32_t);
          const size_t inflate_cap = (size_t)skip + cap;
          uint8_t* inflated = (uint8_t*)malloc(inflate_cap);
          if (!inflated) return CELL_SPURS_TASK_ERROR_NOMEM;
          const int full = edge_inflate(inflated, (uint32_t)inflate_cap,
                                        vm_base + src, srclen);
          if (full < 0) {
              free(inflated);
              fprintf(stderr, "[edge] inflate failed e=0x%08X src=0x%08X len=%u skip=%u cap=%u\n",
                      e, src, srclen, skip, cap);
              return CELL_SPURS_TASK_ERROR_INVAL;
          }
          const u32 count = full > (int)skip ? (u32)full - skip : 0;
          if (count) memcpy(vm_base + dst, inflated + skip, count);
          free(inflated);
          const u32 left = vm_read32(counter);
          if (left) vm_write32(counter, left - 1u);
          if (left == 1u && flag && bits)
              cellSpursEventFlagSet((CellSpursEventFlag*)(uintptr_t)flag, bits);
          static int edge_n = 0;
          if (edge_n++ < 12)
              fprintf(stderr, "[edge] inflate #%d src=0x%08X len=%u skip=%u -> %u bytes\n",
                      edge_n, src, srclen, skip, count);
          return CELL_OK;
      } }

    const uint32_t q = (uint32_t)queue_ea;'''
    if source.count(push_anchor) != 1:
        raise SystemExit("SPURS2 patch cannot find the LFQueue Edge Zlib insertion point")
    source = source.replace(push_anchor, edge_hle, 1)

    # Ascension's libsync SPU consumer reads the SDK CellSyncLFQueue line
    # (direction at +0x24, 2nd-generation push/pop counters at +0x30/+0x50).
    # The old fallback's guessed ring fields overwrite those control bytes.
    queue_init_anchor = '''    uint32_t q = (uint32_t)queue_ea;
    for (uint32_t o = 0; o < 128; o += 4) vm_write32(q + o, 0);

    /* W3 at +0x0C is the ring modulus'''
    queue_init_replacement = '''    uint32_t q = (uint32_t)queue_ea;
    const uint64_t buffer_bytes = (uint64_t)size * (uint64_t)depth;
    if (buffer_bytes > UINT32_MAX ||
        !spurs_guest_range_valid(q, 128) ||
        !spurs_guest_range_valid((uint32_t)buffer_ea, (uint32_t)buffer_bytes))
        return CELL_SPURS_TASK_ERROR_FAULT;
    for (uint32_t o = 0; o < 128; o += 4) vm_write32(q + o, 0);

    /* ASCENSION_M772_LFQUEUE_SDK_LAYOUT_V1: game-proven CellSyncLFQueue
     * state. In ANY2ANY direction, the byte shifters and version/push/pop
     * counters begin in the SDK's all-ones state. */
    { static int s_sdk = -1;
      if (s_sdk < 0) s_sdk = getenv("PS3_LFQUEUE_SDK_LAYOUT") ? 1 : 0;
      if (s_sdk) {
          vm_write32(q + 0x10, size);
          vm_write32(q + 0x14, depth);
          vm_write64(q + 0x18, (u64)(uint32_t)buffer_ea);
          vm_write32(q + 0x24, direction);
          if (direction == 3) {
              vm_write8(q + 0x20, 0xFF); vm_write8(q + 0x21, 0xFF);
              vm_write32(q + 0x28, 0xFFFFFFFFu);
              vm_write16(q + 0x30, 0xFFFF);
              vm_write16(q + 0x50, 0xFFFF);
          } else {
              for (int i = 0; i < 4; i++) vm_write8(q + 0x20 + i, 0xFF);
          }
          vm_write64(q + 0x70, (u64)(uint32_t)owner_ea);
          memset(vm_base + (uint32_t)buffer_ea, 0, (size_t)buffer_bytes);
          printf("[cellSpurs] LFQueueInitialize q=0x%08X dir=%u -> SDK layout\\n", q, direction);
          return CELL_OK;
      } }

    /* W3 at +0x0C is the ring modulus'''
    if source.count(queue_init_anchor) != 1:
        raise SystemExit("SPURS2 patch cannot find the LFQueue initialize insertion point")
    source = source.replace(queue_init_anchor, queue_init_replacement, 1)

    # Bounds-check the normal LFQueue producer before its raw lock-line reads
    # and before it touches the guest buffer. Its call path is also used when
    # the Edge host inflater is disabled.
    normal_push_anchor = '''    const uint32_t q = (uint32_t)queue_ea;
    /* Raw big-endian access while the lock-line lock is held:'''
    normal_push_replacement = '''    const uint32_t q = (uint32_t)queue_ea;
    if (!spurs_guest_range_valid(q, 128) ||
        !spurs_guest_range_valid((uint32_t)data_ea, 16))
        return CELL_SPURS_TASK_ERROR_FAULT;
    /* Raw big-endian access while the lock-line lock is held:'''
    if source.count(normal_push_anchor) != 1:
        raise SystemExit("SPURS2 patch cannot find LFQueue producer bounds-check insertion point")
    source = source.replace(normal_push_anchor, normal_push_replacement, 1)
    queue_buffer_anchor = '''        uint32_t buf = LFQ_R32(q + 0x1C);   /* low word of the u64 at +0x18 */
        if (w3 <= 0 || !sz || !buf) { spu_lockline_unlock(); return CELL_SPURS_TASK_ERROR_INVAL; }'''
    queue_buffer_replacement = '''        uint32_t buf = LFQ_R32(q + 0x1C);   /* low word of the u64 at +0x18 */
        if (w3 <= 0 || !sz || !buf) { spu_lockline_unlock(); return CELL_SPURS_TASK_ERROR_INVAL; }
        const uint64_t bytes = (uint64_t)sz * (uint64_t)w3;
        if (bytes > UINT32_MAX || !spurs_guest_range_valid(buf, (uint32_t)bytes) ||
            !spurs_guest_range_valid((uint32_t)data_ea, sz)) {
            spu_lockline_unlock(); return CELL_SPURS_TASK_ERROR_FAULT;
        }'''
    if source.count(queue_buffer_anchor) != 1:
        raise SystemExit("SPURS2 patch cannot find LFQueue buffer bounds-check insertion point")
    source = source.replace(queue_buffer_anchor, queue_buffer_replacement, 1)

    # Upstream's queue runtime needs the bundled inflater translation unit.
    cmake = upstream / "CMakeLists.txt"
    cmake_text = cmake.read_text(errors="replace")
    cpp_line = '    "libs/codec/edge_inflate.cpp"\n'
    codec_anchor = '    "libs/codec/*.c"\n'
    if cpp_line not in cmake_text:
        if cmake_text.count(codec_anchor) != 1:
            raise SystemExit("SPURS2 patch cannot add Edge Zlib to the HLE source list")
        cmake_text = cmake_text.replace(codec_anchor, codec_anchor + cpp_line, 1)

    source = source.replace("ASCENSION_M772_SPURS2_TASK_API_V1", MARKER)
    declarations = r'''/* ASCENSION_M772_SPURS2_TASK_API_V1 */
s32 cellSpursDestroyTaskset2(CellSpursTaskset* taskset);
s32 cellSpursTasksetGetSpursAddress(const CellSpursTaskset* taskset, u32* spurs_out);
s32 _cellSpursTaskAttribute2Initialize(void* attr, u32 revision);
s32 cellSpursCreateTask2(CellSpursTaskset* taskset, CellSpursTaskId* taskId,
                         void* elf, u32 argument_ea, u32 attr_ea);
s32 cellSpursJoinTask2(CellSpursTaskset* taskset, CellSpursTaskId taskId,
                       s32* exitCode);
s32 cellSpursTryJoinTask2(CellSpursTaskset* taskset, CellSpursTaskId taskId,
                          s32* exitCode);
s32 cellSpursLFQueueDetachLv2EventQueue(u64 queue_ea);
s32 cellSpursGetWorkloadFlag(CellSpurs* spurs, u32* flag_ea_out);
s32 _cellSpursWorkloadFlagReceiver(CellSpurs* spurs, u32 wid, u32 is_set);
'''
    if header.count("cellSpursCreateTask2(") == 0:
        header_anchor = "s32 cellSpursDestroyTaskset(CellSpursTaskset* taskset);"
        if header.count(header_anchor) != 1:
            raise SystemExit("SPURS2 patch cannot add versioned API declarations")
        header = header.replace(header_anchor, header_anchor + "\n" + declarations, 1)
    header = header.replace("ASCENSION_M772_SPURS2_TASK_API_V1", MARKER)

    # The split-queue detach is a bookkeeping no-op in this runtime, matching
    # the already implemented LFQueue attach path. Add it only once.
    detach = '''s32 cellSpursLFQueueDetachLv2EventQueue(u64 queue_ea)
{
    (void)queue_ea;
    return CELL_OK;
}

'''
    detach_anchor = "s32 cellSpursLFQueueAttachLv2EventQueue(u64 queue_ea)"
    if source.count("s32 cellSpursLFQueueDetachLv2EventQueue(") == 0:
        if source.count(detach_anchor) != 1:
            raise SystemExit("SPURS2 patch cannot find the LFQueue detach insertion point")
        source = source.replace(detach_anchor, detach + detach_anchor, 1)
    if "s32 _cellSpursLFQueuePushBody(u64 queue_ea, u64 data_ea, u32 isBlocking);" not in header:
        header_anchor = "s32 _cellSpursLFQueueInitialize(u64 owner_ea, u64 queue_ea, u64 buffer_ea,"
        idx = header.find(header_anchor)
        if idx < 0:
            raise SystemExit("SPURS2 patch cannot find LFQueue declarations")
        end = header.find("\n", header.find("u32 size, u32 depth, u32 direction);", idx))
        if end < 0:
            raise SystemExit("SPURS2 patch cannot find LFQueue declaration terminator")
        header = header[:end + 1] + "s32 _cellSpursLFQueuePushBody(u64 queue_ea, u64 data_ea, u32 isBlocking);\n" + header[end + 1:]
    if "cellSpursLFQueueDetachLv2EventQueue(u64 queue_ea);" not in header:
        anchor = "s32 cellSpursLFQueueAttachLv2EventQueue(u64 queue_ea);"
        if header.count(anchor) != 1:
            raise SystemExit("SPURS2 patch cannot add LFQueue detach declaration")
        header = header.replace(anchor, anchor + "\ns32 cellSpursLFQueueDetachLv2EventQueue(u64 queue_ea);", 1)

    c.write_text(source)
    h.write_text(header)
    (upstream / "runtime/spu/spu_workload.c").write_text(workload_source)
    cmake.write_text(cmake_text)

    upstream_inflater = upstream / "libs/codec/edge_inflate.cpp"
    inflater_src = repo / "runtime/edge_inflate.cpp"
    if not upstream_inflater.exists():
        upstream_inflater.write_bytes(inflater_src.read_bytes())
    elif upstream_inflater.read_bytes() != inflater_src.read_bytes():
        raise SystemExit("pinned upstream already has a different edge_inflate.cpp")


def apply_pm_resolution_diagnostics(upstream: pathlib.Path) -> None:
    """Expose the exact guest PM identity that the SPURS scheduler hashes.

    M7.84's 5/5 registry check only proved that five expected fingerprints
    were compiled into the table. It did not report the fingerprint, range,
    or size actually passed by cellSpursAddWorkload, so a device could show
    0/18 PM matches without revealing which executable bytes were missing.
    """
    source_path = upstream / "libs/spurs/cellSpurs.c"
    source = source_path.read_text(errors="replace")
    if PM_DIAGNOSTICS_MARKER in source:
        required = ("cellSpursCopyAscensionPmDiagnostics", "s_asc_pm_diag",
                    "spurs_guest_range_valid(pm_ea, w->sizePm)")
        missing = [needle for needle in required if needle not in source]
        if missing:
            raise SystemExit(f"partial SPURS PM diagnostics: {missing}")
        return

    metric_decl = "static volatile u64 s_asc_dispatches, s_asc_dispatches_hi;\n"
    diagnostic_decl = "static volatile u64 s_asc_pm_diag[SPURS_MAX_WID][7];\n"
    if source.count(metric_decl) != 1:
        raise SystemExit("SPURS PM diagnostics could not locate the M7.84 metrics declaration")
    source = source.replace(metric_decl, metric_decl + diagnostic_decl, 1)

    reset_anchor = "    __atomic_store_n(&s_asc_last_dispatch_wid, UINT64_MAX, __ATOMIC_RELAXED);\n"
    reset_lines = '''    for (u32 wid = 0; wid < SPURS_MAX_WID; ++wid) {
        __atomic_store_n(&s_asc_pm_diag[wid][0], UINT64_MAX, __ATOMIC_RELEASE);
        for (u32 field = 1; field < 7; ++field)
            __atomic_store_n(&s_asc_pm_diag[wid][field], 0, __ATOMIC_RELAXED);
    }
'''
    if source.count(reset_anchor) != 1:
        raise SystemExit("SPURS PM diagnostics could not locate the metrics reset")
    source = source.replace(reset_anchor, reset_anchor + reset_lines, 1)

    copy_anchor = "    out[7]=__atomic_load_n(&s_asc_last_dispatch_wid,__ATOMIC_RELAXED);\n}\n"
    copy_api = '''
void cellSpursCopyAscensionPmDiagnostics(u64 out[SPURS_MAX_WID][7]) {
    if (!out) return;
    for (u32 wid = 0; wid < SPURS_MAX_WID; ++wid) {
        out[wid][0]=__atomic_load_n(&s_asc_pm_diag[wid][0],__ATOMIC_ACQUIRE);
        for (u32 field = 1; field < 7; ++field)
            out[wid][field]=__atomic_load_n(&s_asc_pm_diag[wid][field],__ATOMIC_RELAXED);
    }
}
'''
    if source.count(copy_anchor) != 1:
        raise SystemExit("SPURS PM diagnostics could not locate the M7.84 metrics copy API")
    source = source.replace(copy_anchor, copy_anchor + copy_api, 1)

    old_fp = '''    uint64_t fp = spu_workload_fingerprint(vm_base + (uint32_t)(uintptr_t)w->pm,
                                           w->sizePm);
    r->fn = spu_workload_find_img(fp, &r->image_id);
'''
    new_fp = f'''    uintptr_t pm_pointer = (uintptr_t)w->pm;
    u32 pm_ea = (u32)pm_pointer;
    u32 pointer_high = pm_pointer > UINT32_MAX;
    u32 range_ok = !pointer_high && spurs_guest_range_valid(pm_ea, w->sizePm);
    uint64_t fp = range_ok ? spu_workload_fingerprint(vm_base + pm_ea,
                                                       w->sizePm) : 0;
    r->fn = range_ok ? spu_workload_find_img(fp, &r->image_id) : NULL;
    if (!range_ok) r->image_id = 0;
    __atomic_store_n(&s_asc_pm_diag[wid][0], UINT64_MAX, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_pm_diag[wid][1], pm_ea, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_pm_diag[wid][2], w->sizePm, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_pm_diag[wid][3], fp, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_pm_diag[wid][4], r->image_id, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_pm_diag[wid][5], range_ok, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_pm_diag[wid][6], pointer_high, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_pm_diag[wid][0], wid, __ATOMIC_RELEASE);
'''
    if source.count(old_fp) != 1:
        raise SystemExit("SPURS PM diagnostics could not locate the runtime fingerprint lookup")
    source = source.replace(old_fp, new_fp, 1)
    source = source.replace("/* ASCENSION_M772_SPURS2_WORKLOADS_32_V1 */",
                            "/* ASCENSION_M772_SPURS2_WORKLOADS_32_V1 */\n/* "
                            + PM_DIAGNOSTICS_MARKER + " */", 1)
    source_path.write_text(source)


def apply_requested_pm_capture(upstream: pathlib.Path) -> None:
    """Save a requested but unassociated SPURS PM for exact native relifting.

    The runtime's SPU_DUMP_MISS directory is already created inside Documents
    and exported by the launcher. A PM is captured only after the game submits
    it to SPURS and its exact fingerprint has no matching native lift.
    """
    path = upstream / "libs/spurs/cellSpurs.c"
    source = path.read_text(errors="replace")
    if PM_CAPTURE_MARKER in source:
        required = ("cellSpursCaptureAscensionPmMiss", "spupm_%016llX_%u.bin",
                    "cellSpursCaptureAscensionPmMiss(fp, vm_base + pm_ea, w->sizePm)")
        missing = [marker for marker in required if marker not in source]
        if missing:
            raise SystemExit(f"partial requested PM capture patch: {missing}")
        return

    anchor = "static WklPm* spurs_resolve_pm(u32 wid)\n{"
    if source.count(anchor) != 1:
        raise SystemExit("M7.88 cannot locate the SPURS PM resolver")
    helper = r'''/* ASCENSION_M788_CAPTURE_REQUESTED_PM_V1
 * The iPhone's C8D774 runtime image is not byte-identical to the NPUA
 * CE052AC lift. Save only a PM the title actually submitted and the native
 * registry could not associate; this is source for the next exact lift, not
 * evidence that a job ran. */
void cellSpursCaptureAscensionPmMiss(u64 fingerprint, const u8* image, u32 size)
{
    const char* dir = getenv("SPU_DUMP_MISS");
    if (!dir || !*dir || !image || !fingerprint || !size || size > 0x01000000u)
        return;
    static volatile u64 dumped[64];
    unsigned slot = 64;
    for (unsigned i = 0; i < 64; ++i) {
        u64 seen = __atomic_load_n(&dumped[i], __ATOMIC_ACQUIRE);
        if (seen == fingerprint) return;
        if (seen == 0) {
            u64 empty = 0;
            if (__atomic_compare_exchange_n(&dumped[i], &empty, fingerprint, 0,
                                             __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
                slot = i;
                break;
            }
            if (empty == fingerprint) return;
        }
    }
    if (slot == 64) return;
    char filename[512];
    snprintf(filename, sizeof(filename), "%s/spupm_%016llX_%u.bin", dir,
             (unsigned long long)fingerprint, size);
    FILE* out = fopen(filename, "wb");
    if (!out) {
        __atomic_store_n(&dumped[slot], 0, __ATOMIC_RELEASE);
        fprintf(stderr, "[spurs-pm] requested PM capture failed: %s\n", filename);
        return;
    }
    size_t written = fwrite(image, 1, size, out);
    fclose(out);
    if (written != size) {
        remove(filename);
        __atomic_store_n(&dumped[slot], 0, __ATOMIC_RELEASE);
        fprintf(stderr, "[spurs-pm] requested PM capture was short: %s (%zu/%u)\n",
                filename, written, size);
        return;
    }
    fprintf(stderr, "[spurs-pm] requested unassociated PM captured: %s\n", filename);
}

'''
    source = source.replace(anchor, helper + anchor, 1)
    lookup = '''    r->fn = range_ok ? spu_workload_find_img(fp, &r->image_id) : NULL;
    if (!range_ok) r->image_id = 0;
'''
    replacement = '''    r->fn = range_ok ? spu_workload_find_img(fp, &r->image_id) : NULL;
    if (range_ok && !r->fn)
        cellSpursCaptureAscensionPmMiss(fp, vm_base + pm_ea, w->sizePm);
    if (!range_ok) r->image_id = 0;
'''
    if source.count(lookup) != 1:
        raise SystemExit("M7.88 cannot attach capture to the unresolved requested PM")
    source = source.replace(lookup, replacement, 1)
    path.write_text(source)


def apply_ascension_wws_policy(upstream: pathlib.Path) -> None:
    """Port the Ascension-proven WWS/SPURS behavior from the PC port.

    M7.85's live report identifies the WWS PM by the same 12 KiB raw image
    fingerprint documented by the PC port. That makes the next two SPURS
    behaviors directly relevant: Wws modules read CellSpurs flags from the
    kernel tempArea, and their readyCount is a level rather than a token that
    the host scheduler consumes on admission.
    """
    spurs_path = upstream / "libs/spurs/cellSpurs.c"
    spurs = spurs_path.read_text(errors="replace")
    channels_path = upstream / "runtime/spu/spu_channels.c"
    channels = channels_path.read_text(errors="replace")
    policy_path = upstream / "runtime/spu/spurs_policy.c"
    policy = policy_path.read_text(errors="replace")

    if ASCENSION_POLICY_MARKER in spurs:
        required = (
            "spurs_poll_select", "spurs_ready_level() ? ready > si->active[wid]",
            "spurs_kernel_temp_area_refresh(ctx)",
        )
        if any(marker not in spurs + channels + policy for marker in required):
            raise SystemExit("partial Ascension WWS/SPURS tempArea/ready-level patch")
        return
    if any(ASCENSION_POLICY_MARKER in text for text in (channels, policy)):
        raise SystemExit("partial Ascension WWS/SPURS tempArea/ready-level patch")

    helper = '''/* ASCENSION_M786_WWS_TEMPA_READY_LEVEL_V1
 * The Ascension PC port's WWS PM reads CellSpurs flags from LS tempArea and
 * treats readyCount as a level. Keep the option game-specific and disabled
 * unless the iOS Ascension launcher enables SPURS_READY_LEVEL. */
int spurs_ready_level(void)
{
    static int s_level = -1;
    if (s_level < 0) {
        const char* value = getenv("SPURS_READY_LEVEL");
        s_level = value && *value != '0';
    }
    return s_level;
}

/* Select the workload cellSpursModulePoll should continue on this SPU. */
u32 spurs_poll_select(u32 ea, u32 current, u32 spu)
{
    struct SpursInst* si = spurs_inst_find(ea);
    if (!si || spu >= CELL_SPURS_MAX_SPU) return 0x20u;
    const u32 nwid = spurs_workload_limit(si);
    const u32 enabled = vm_read32(ea + SPURS_WKL_ENABLED);
    u32 selected = 0x20u;
    for (u32 wid = 0; wid < nwid; ++wid) {
        if (!(enabled & (0x80000000u >> wid)) ||
            vm_read8(ea + wkl_state_off(wid)) != 2 ||
            !s_workloads[wid].in_use || s_workloads[wid].spurs_ea != ea ||
            !vm_read8(ea + wkl_info_off(wid) + 0x18 + spu))
            continue;
        const u32 ready = vm_read8(ea + wkl_ready_off(wid));
        const int signalled = wkl_signalled(ea, wid);
        if (wid == current) {
            if (signalled || ready >= si->active[wid]) return current;
        } else if (selected == 0x20u && (signalled || ready > si->active[wid])) {
            selected = wid;
        }
    }
    return selected;
}

'''
    scheduler_anchor = "static DWORD WINAPI spurs_kernel_thread(LPVOID p)\n{"
    if spurs.count(scheduler_anchor) != 1:
        raise SystemExit("Ascension WWS patch cannot find the SPURS scheduler")
    spurs = spurs.replace(scheduler_anchor, helper + scheduler_anchor, 1)

    start = spurs.index(scheduler_anchor)
    end = spurs.index("\nstatic s32 spurs_scheduler_start", start)
    scheduler = spurs[start:end]
    old_spu_loop = "        for (u32 sn = 0; sn < si->nspus; sn++) {\n"
    new_spu_loop = '''        /* WWS keeps pipeline state in the local store of the SPU that ran it. */
        const u32 first_spu = spurs_ready_level() ? si->pass_no % si->nspus : 0;
        for (u32 k = 0; k < si->nspus; ++k) {
            const u32 sn = (first_spu + k) % si->nspus;
'''
    if scheduler.count(old_spu_loop) != 1:
        raise SystemExit("Ascension WWS patch cannot locate scheduler SPU scan")
    scheduler = scheduler.replace(old_spu_loop, new_spu_loop, 1)
    old_kicked = "                int kicked = ready || wkl_signalled(ea, wid);\n"
    new_kicked = "                int kicked = (spurs_ready_level() ? ready > si->active[wid] : ready != 0)\n                             || wkl_signalled(ea, wid);\n"
    if scheduler.count(old_kicked) != 1:
        raise SystemExit("Ascension WWS patch cannot locate readyCount admission")
    scheduler = scheduler.replace(old_kicked, new_kicked, 1)
    old_consume = "                if (ready) vm_base[ea + wkl_ready_off(wid)] = (u8)(ready - 1);\n"
    new_consume = "                if (ready && !spurs_ready_level())\n                    vm_base[ea + wkl_ready_off(wid)] = (u8)(ready - 1);\n"
    if scheduler.count(old_consume) != 1:
        raise SystemExit("Ascension WWS patch cannot locate readyCount consumption")
    scheduler = scheduler.replace(old_consume, new_consume, 1)
    spurs = spurs[:start] + scheduler + spurs[end:]
    spurs_path.write_text(spurs)

    temparea = '''/* Ascension WWS reads the first 128 CellSpurs bytes from LS tempArea. */
void spurs_kernel_temp_area_refresh(spu_context* ctx)
{
    extern uint8_t* vm_base;
    if (!ctx || !ctx->ls) return;
    const uint8_t* field = ctx->ls + 0x1C4; /* CellSpurs EA, low half of u64 */
    const uint32_t ea = ((uint32_t)field[0] << 24) | ((uint32_t)field[1] << 16) |
                        ((uint32_t)field[2] << 8) | field[3];
    if (!vm_base || !ea || ea > 0xFFFFFF80u) return;
    spu_lockline_lock();
    memcpy(ctx->ls + 0x100, vm_base + ea, 0x80);
    spu_lockline_unlock();
}

'''
    policy_anchor = "extern int spu_run_with_halt(void (*)(spu_context*), spu_context*);\n"
    if policy.count(policy_anchor) != 1:
        raise SystemExit("Ascension WWS patch cannot find policy runtime declarations")
    policy = policy.replace(policy_anchor, policy_anchor + "\n" + temparea, 1)
    init_anchor = "#undef KBE32\n\n    /* Entry registers per cellSpursModuleEntry. */"
    if policy.count(init_anchor) != 1:
        raise SystemExit("Ascension WWS patch cannot locate policy entry context setup")
    policy = policy.replace(init_anchor,
                            "#undef KBE32\n    spurs_kernel_temp_area_refresh(ctx);\n\n"
                            "    /* Entry registers per cellSpursModuleEntry. */", 1)
    policy_path.write_text(policy)

    poll_anchor = '''            ctx->gpr[3] = spu_make_preferred_u32(0);
            ctx->pc = ctx->gpr[0]._u32[0] & SPU_LS_MASK;
'''
    poll_replacement = '''            /* Refresh the kernel context snapshot at every workload selection. */
            extern void spurs_kernel_temp_area_refresh(spu_context*);
            spurs_kernel_temp_area_refresh(ctx);
            /* SPURS returns the selected workload in the preferred high word. */
            extern int spurs_ready_level(void);
            extern uint32_t spurs_poll_select(uint32_t, uint32_t, uint32_t);
            uint32_t selected = 0;
            if (spurs_ready_level()) {
                const uint8_t* p = ctx->ls + 0x1C4;
                const uint32_t ea = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
                                    ((uint32_t)p[2] << 8) | p[3];
                p = ctx->ls + 0x1C8;
                const uint32_t spu = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
                                     ((uint32_t)p[2] << 8) | p[3];
                p = ctx->ls + 0x1DC;
                const uint32_t current = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
                                         ((uint32_t)p[2] << 8) | p[3];
                selected = spurs_poll_select(ea, current, spu);
            }
            ctx->gpr[3] = spu_make_preferred_u32(0);
            ctx->gpr[3]._u32[0] = selected;
            ctx->gpr[3]._u32[1] = 0;
            ctx->pc = ctx->gpr[0]._u32[0] & SPU_LS_MASK;
'''
    if channels.count(poll_anchor) != 1:
        raise SystemExit("Ascension WWS patch cannot locate module-poll intercept")
    channels = channels.replace(poll_anchor, poll_replacement, 1)
    channels = channels.replace("/* SPURS kernel services (policy-module runs only):",
                                "/* ASCENSION_M786_WWS_TEMPA_READY_LEVEL_V1 */\n"
                                "    /* SPURS kernel services (policy-module runs only):", 1)
    channels_path.write_text(channels)


def apply_ascension_workload_flag_scheduler(upstream: pathlib.Path) -> None:
    """Match the US Ascension SPURS workload-flag ownership and wake path.

    The iOS HLE already exposes cellSpursGetWorkloadFlag and
    _cellSpursWorkloadFlagReceiver, but its initializer set +0x60 instead of
    the flag value at +0x6C and left receiver +0x77 as zero. The PC fork
    initializes +0x6C to all ones and +0x77 to NONE, then consumes a zero flag
    for its registered workload in the scheduler. Keep the whole protocol in
    the runtime that is compiled into the iOS IPA.
    """
    path = upstream / "libs/spurs/cellSpurs.c"
    source = path.read_text(errors="replace")
    if WORKLOAD_FLAG_MARKER in source:
        required = ("SPURS_WKL_FLAG_VAL = 0x6C", "SPURS_WKL_FLAG_RCV = 0x77",
                    "spurs_workload_flag_take(ea, wid)",
                    "int kicked = flagged ||")
        if any(token not in source for token in required):
            raise SystemExit("partial Ascension SPURS workload-flag patch")
        return

    enum_anchor = "    SPURS_WKL_FLAG     = 0x60,\n"
    enum_new = (enum_anchor + "    SPURS_WKL_FLAG_VAL = 0x6C,\n"
                "    SPURS_WKL_FLAG_RCV = 0x77,\n")
    if source.count(enum_anchor) != 1:
        raise SystemExit("M7.99 cannot locate CellSpurs workload-flag offsets")
    source = source.replace(enum_anchor, enum_new, 1)

    init_old = "    vm_write64(spurs_ea + SPURS_WKL_FLAG, 0xFFFFFFFFFFFFFFFFull); /* no receiver */\n"
    init_new = "    vm_write32(spurs_ea + SPURS_WKL_FLAG_VAL, 0xFFFFFFFFu);\n    vm_write8(spurs_ea + SPURS_WKL_FLAG_RCV, 0xFFu);\n"
    if source.count(init_old) != 1:
        raise SystemExit("M7.99 cannot locate the incorrect workload-flag initialization")
    source = source.replace(init_old, init_new, 1)

    helper_anchor = "static DWORD WINAPI spurs_kernel_thread(LPVOID p)\n{"
    helper = '''/* ASCENSION_M799_SPURS_WORKLOAD_FLAG_V1 */
int spurs_workload_flag_take(u32 ea, u32 wid)
{
    int flagged = 0;
    const u32 value_ea = ea + SPURS_WKL_FLAG_VAL;
    const u32 receiver_ea = ea + SPURS_WKL_FLAG_RCV;
    spu_lockline_lock();
    /* Raw BE access: vm_* takes this same nonrecursive lock. */
    const u32 value = ((u32)vm_base[value_ea] << 24) |
                      ((u32)vm_base[value_ea + 1] << 16) |
                      ((u32)vm_base[value_ea + 2] << 8) |
                       (u32)vm_base[value_ea + 3];
    if (value == 0 && vm_base[receiver_ea] == (u8)wid) {
        vm_base[value_ea + 0] = 0xFFu;
        vm_base[value_ea + 1] = 0xFFu;
        vm_base[value_ea + 2] = 0xFFu;
        vm_base[value_ea + 3] = 0xFFu;
        flagged = 1;
    }
    ef_line_end(ea);
    return flagged;
}

'''
    if source.count(helper_anchor) != 1:
        raise SystemExit("M7.99 cannot locate the SPURS scheduler insertion point")
    source = source.replace(helper_anchor, helper + helper_anchor, 1)

    kicked_old = '''                int kicked = (spurs_ready_level() ? ready > si->active[wid] : ready != 0)
                             || wkl_signalled(ea, wid);
'''
    kicked_new = '''                const int flagged = spurs_workload_flag_take(ea, wid);
                int kicked = flagged ||
                             (spurs_ready_level() ? ready > si->active[wid] : ready != 0) ||
                             wkl_signalled(ea, wid);
'''
    if source.count(kicked_old) != 1:
        raise SystemExit("M7.99 cannot locate the WWS workload admission condition")
    source = source.replace(kicked_old, kicked_new, 1)
    source = source.replace("/* ASCENSION_M772_SPURS2_WORKLOADS_32_V1 */",
                            "/* ASCENSION_M772_SPURS2_WORKLOADS_32_V1 */\n"
                            "/* " + WORKLOAD_FLAG_MARKER + " */", 1)
    path.write_text(source)


def apply_taskset_context_workload_id(upstream: pathlib.Path) -> None:
    """Match the US port's taskset context ABI for SPU task-library fast paths.

    Its lifted SPU task library reads the active workload id from LS +0x1DC.
    The pinned iOS runtime built the surrounding context but left this word
    zero, so task APIs could reject/park work even though a WWS PM was admitted.
    """
    path = upstream / "libs/spurs/spurs_pm.c"
    source = path.read_text(errors="replace")
    assignment = "LS_BE32(0x1DC, vm_read32(taskset_ea + CSTS_WID));"
    if TASKSET_WID_MARKER in source:
        if assignment not in source:
            raise SystemExit("partial M8.00 taskset workload-id context patch")
        return

    anchor = "    LS_BE32(STC_DMA_TAG_ID,   dmaTagId);\n"
    if source.count(anchor) != 1:
        raise SystemExit("M8.00 cannot locate the SPURS taskset context header")
    replacement = anchor + (
        "    /* " + TASKSET_WID_MARKER + "\n"
        "     * The US GoWA runtime writes the taskset's workload id into the\n"
        "     * SPU task-library kernel context. The library uses LS +0x1DC to\n"
        "     * validate task API calls and route workload-scoped signals. */\n"
        "    " + assignment + "\n"
    )
    source = source.replace(anchor, replacement, 1)
    path.write_text(source)


def apply_job_dispatch_metrics(upstream: pathlib.Path) -> None:
    """Measure actual game job dispatches separately from WWS PM admissions."""
    path = upstream / "runtime/spu/spu_workload.c"
    source = path.read_text(errors="replace")
    if JOB_METRICS_MARKER in source:
        required = ("spu_workload_reset_ascension_job_metrics",
                    "spu_workload_copy_ascension_job_metrics",
                    "s_asc_job_misses", "s_asc_job_completed")
        missing = [name for name in required if name not in source]
        if missing:
            raise SystemExit(f"partial SPURS job metrics patch: {missing}")
        return

    anchor = "int spu_workload_dispatch_job(const uint8_t* image, uint32_t image_size,\n"
    if source.count(anchor) != 1:
        raise SystemExit("M7.87 cannot locate the SPURS job dispatch entry")
    api = '''/* ASCENSION_M787_SPURS_JOB_METRICS_V1 */
extern uint8_t* vm_base;
static volatile uint64_t s_asc_job_calls, s_asc_job_hits, s_asc_job_misses;
static volatile uint64_t s_asc_job_completed, s_asc_job_active;
static volatile uint64_t s_asc_job_last_fp, s_asc_job_last_size, s_asc_job_last_ea;
void spu_workload_reset_ascension_job_metrics(void) {
    __atomic_store_n(&s_asc_job_calls, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_hits, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_misses, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_completed, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_active, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_last_fp, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_last_size, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_last_ea, 0, __ATOMIC_RELAXED);
}
void spu_workload_copy_ascension_job_metrics(uint64_t out[8]) {
    if (!out) return;
    const uintptr_t image = (uintptr_t)__atomic_load_n(&s_asc_job_last_ea, __ATOMIC_RELAXED);
    const uintptr_t base = (uintptr_t)vm_base;
    out[0] = __atomic_load_n(&s_asc_job_calls, __ATOMIC_RELAXED);
    out[1] = __atomic_load_n(&s_asc_job_hits, __ATOMIC_RELAXED);
    out[2] = __atomic_load_n(&s_asc_job_misses, __ATOMIC_RELAXED);
    out[3] = __atomic_load_n(&s_asc_job_completed, __ATOMIC_RELAXED);
    out[4] = __atomic_load_n(&s_asc_job_active, __ATOMIC_RELAXED);
    out[5] = __atomic_load_n(&s_asc_job_last_fp, __ATOMIC_RELAXED);
    out[6] = __atomic_load_n(&s_asc_job_last_size, __ATOMIC_RELAXED);
    out[7] = base && image >= base && image - base <= UINT32_MAX ? image - base : 0;
}
'''
    source = source.replace(anchor, api + "\n" + anchor, 1)
    job_start = source.index(anchor)

    fp_anchor = '''    uint64_t fp = spu_workload_fingerprint(image, image_size);
    spu_lifted_entry_fn fn = NULL;
    int image_id = 0;
'''
    fp_replacement = '''    uint64_t fp = spu_workload_fingerprint(image, image_size);
    __atomic_add_fetch(&s_asc_job_calls, 1, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_last_fp, fp, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_last_size, image_size, __ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_job_last_ea, (uint64_t)(uintptr_t)image, __ATOMIC_RELAXED);
    spu_lifted_entry_fn fn = NULL;
    int image_id = 0;
'''
    fp_pos = source.find(fp_anchor, job_start)
    if fp_pos < 0:
        raise SystemExit("M7.87 cannot instrument SPURS job fingerprint")
    source = source[:fp_pos] + fp_replacement + source[fp_pos + len(fp_anchor):]

    miss_anchor = '''        return 0;
    }
    /* Two lines plus two explicit flushes PER JOB.'''
    miss_pos = source.find(miss_anchor, job_start)
    if miss_pos < 0:
        raise SystemExit("M7.87 cannot instrument unresolved SPURS job modules")
    source = source[:miss_pos] + '''        __atomic_add_fetch(&s_asc_job_misses, 1, __ATOMIC_RELAXED);
''' + source[miss_pos:]

    hit_anchor = '''    int verbose = ps3_log_verbose();
    if (verbose) {
'''
    hit_pos = source.find(hit_anchor, job_start)
    if hit_pos < 0:
        raise SystemExit("M7.87 cannot instrument resolved SPURS job modules")
    source = source[:hit_pos] + '''    __atomic_add_fetch(&s_asc_job_hits, 1, __ATOMIC_RELAXED);
    __atomic_add_fetch(&s_asc_job_active, 1, __ATOMIC_RELAXED);
''' + source[hit_pos:]

    complete_anchor = '''    int rc = spu_run_spurs_job(fn, image_id, job_ea, job_desc_size);
    if (verbose) {
'''
    complete_pos = source.find(complete_anchor, job_start)
    if complete_pos < 0:
        raise SystemExit("M7.87 cannot instrument SPURS job completion")
    complete_replacement = '''    int rc = spu_run_spurs_job(fn, image_id, job_ea, job_desc_size);
    __atomic_add_fetch(&s_asc_job_completed, 1, __ATOMIC_RELAXED);
    __atomic_sub_fetch(&s_asc_job_active, 1, __ATOMIC_RELAXED);
    if (verbose) {
'''
    source = source[:complete_pos] + complete_replacement + source[complete_pos + len(complete_anchor):]
    path.write_text(source)


def apply_dynamic_wws_pm_role(upstream: pathlib.Path) -> None:
    """Route WWS policy hooks by registered PM identity, not image 2.

    The pinned upstream's job-overlay path assumes image 2, while this title
    registers NPUA and observed C8 policy images as images 5 and 6. Track every
    registered WWS PM so either exact policy can dispatch the lifted overlays.
    """
    workload_path = upstream / "runtime/spu/spu_workload.c"
    channels_path = upstream / "runtime/spu/spu_channels.c"
    dma_path = upstream / "runtime/spu/spu_dma.h"
    workload = workload_path.read_text(errors="replace")
    channels = channels_path.read_text(errors="replace")
    dma = dma_path.read_text(errors="replace")

    role_helper = '''/* ASCENSION_M790_DYNAMIC_WWS_PM_ROLE_V1
 * Preserve the legacy image 2 fallback and add each WWS policy image named by
 * this title (NPUA=5 and the separately observed C8 policy=6).
 */
uint64_t g_spu_wws_pm_image_mask = UINT64_C(1) << 2;

int spu_workload_is_wws_pm_image(int image_id)
{
    return image_id >= 0 && image_id < 64 &&
           (g_spu_wws_pm_image_mask & (UINT64_C(1) << image_id)) != 0;
}

static void spu_workload_note_wws_role(int image_id, const char* name)
{
    if (!name) return;
    if (image_id >= 0 && image_id < 64 &&
        (strncmp(name, "pm_wwsjob", 9) == 0 || strncmp(name, "wws_pm_", 7) == 0))
        g_spu_wws_pm_image_mask |= UINT64_C(1) << image_id;
}
'''
    registry_anchor = "static unsigned           s_registry_count = 0;\n"
    if DYNAMIC_WWS_PM_MARKER not in workload:
        if workload.count(registry_anchor) != 1:
            raise SystemExit("M7.90 cannot anchor dynamic WWS role in workload registry")
        workload = workload.replace(registry_anchor, registry_anchor + "\n" + role_helper, 1)
        register_anchor = "    if (!fn) return;\n"
        if workload.count(register_anchor) != 1:
            raise SystemExit("M7.90 cannot attach WWS role detection to image registration")
        workload = workload.replace(register_anchor,
                                    register_anchor + "    spu_workload_note_wws_role(image_id, name);\n", 1)
    elif "spu_workload_note_wws_role(image_id, name);" not in workload:
        raise SystemExit("partial M7.90 dynamic WWS role patch in spu_workload.c")

    if "spu_workload_is_wws_pm_image" not in dma:
        include_anchor = "#ifdef __cplusplus\nextern \"C\" {\n#endif\n"
        if dma.count(include_anchor) != 1:
            raise SystemExit("M7.90 cannot declare WWS role for SPU DMA hooks")
        dma = dma.replace(include_anchor,
                          include_anchor + "int spu_workload_is_wws_pm_image(int image_id);\n", 1)

    # These five checks are the policy-specific overlay dispatch, null-job,
    # completion, and return paths. Other image id 2 checks are diagnostics.
    channel_new = "spu_workload_is_wws_pm_image(ctx->image_id)"
    channels = channels.replace(
        "/* WWS job-code overlay match: the PM (image 2) streams a job module into the",
        "/* WWS job-code overlay match: a registered WWS PM streams a job module into the")
    channels = channels.replace(
        "/* WWS job-code fallback: the jobmanager PM (image 2) stages each job's",
        "/* WWS job-code fallback: the registered jobmanager PM stages each job's")
    if DYNAMIC_WWS_PM_MARKER not in channels:
        channel_pattern = re.compile(r"ctx->image_id == 2(?![0-9])")
        count = len(channel_pattern.findall(channels))
        if count != 5:
            raise SystemExit(f"M7.90 WWS channel id checks changed: {count}, expected 5")
        channels = channel_pattern.sub(channel_new, channels)
        channels = channels.replace("/* WWS job-code overlay match:",
                                    "/* ASCENSION_M790_DYNAMIC_WWS_PM_ROLE_V1 */\n"
                                    "    /* WWS job-code overlay match:", 1)
    elif channel_new not in channels or DYNAMIC_WWS_PM_MARKER not in channels:
        raise SystemExit("partial M7.90 WWS role dispatch patch in spu_channels.c")

    dma_new = "spu_workload_is_wws_pm_image(spu->image_id)"
    if DYNAMIC_WWS_PM_MARKER not in dma:
        dma_pattern = re.compile(r"spu->image_id == 2(?![0-9])")
        count = len(dma_pattern.findall(dma))
        if count != 2:
            raise SystemExit(f"M7.90 WWS DMA id checks changed: {count}, expected 2")
        dma = dma_pattern.sub(dma_new, dma)
        dma = dma.replace("/* wwsjob batch-fetch probe:",
                          "/* ASCENSION_M790_DYNAMIC_WWS_PM_ROLE_V1 */\n"
                          "    /* wwsjob batch-fetch probe:", 1)
    elif dma_new not in dma or DYNAMIC_WWS_PM_MARKER not in dma:
        raise SystemExit("partial M7.90 WWS role DMA patch in spu_dma.h")

    workload_path.write_text(workload)
    channels_path.write_text(channels)
    dma_path.write_text(dma)


def apply_lwcond_wait_signal_semantics(upstream: pathlib.Path) -> None:
    """Implement real wait/signal behavior for the game's active lwcond path.

    M7.90's device trace repeatedly enters sys_lwcond_wait from the title, while
    the pinned HLE returned success after a 1 ms poll and made every signal a
    no-op. That violates the PS3 contract and can make condition-protected work
    appear complete before its producer signals it. The guest must release its
    associated lwmutex while parked and reacquire it before returning.
    """
    path = upstream / "runtime/ppu/ppu_sysprx.cpp"
    source = path.read_text(errors="replace")
    required = (LWCOND_SEMANTICS_MARKER, "std::condition_variable",
                "waiter.cv.wait(guard", "waiter.cv.wait_for(guard")
    if LWCOND_SEMANTICS_MARKER in source:
        missing = [needle for needle in required if needle not in source]
        if missing:
            raise SystemExit(f"partial M7.91 lwcond patch: {missing}")
        return

    includes_anchor = "#include <string.h>\n"
    if source.count(includes_anchor) != 1:
        raise SystemExit("M7.91 cannot anchor lwcond synchronization includes")
    source = source.replace(includes_anchor, includes_anchor +
                            "#include <atomic>\n#include <chrono>\n"
                            "#include <condition_variable>\n#include <mutex>\n", 1)

    old_block = '''/* sys_lwcond (sysPrxForUser) — guest-side condition variable, paired with an
 * lwmutex. The CRT and (newly) libsre's cellSpurs create/wait/signal these. Like
 * sys_lwmutex above, model it directly in guest memory so the args stay GUEST
 * EAs (the generic adapter would pass them raw and the C sysPrxForUser impl
 * deref'd them as host pointers -> AV during cellSpurs init). A no-op wait is
 * adequate here: the CRT/SPURS paths that reach us use these for one-shot init
 * handshakes, not long-term blocking. sys_lwcond_t is 8 bytes: +0x00 u32
 * lwmutex EA, +0x04 u32 lwcond queue id. Titles read +0x00 themselves (an
 * lwcond whose lwmutex reads 0 is treated as invalid). */
static void sys_lwcond_create(ppu_context* ctx)
{
    static uint32_t s_lwcond_id = 0x4C000000u;
    uint32_t lwcond  = (uint32_t)ctx->gpr[3];
    uint32_t lwmutex = (uint32_t)ctx->gpr[4];
    vm_write32(lwcond + 0x00, lwmutex);
    vm_write32(lwcond + 0x04, ++s_lwcond_id);
    ctx->gpr[3] = 0;
}
static void sys_lwcond_destroy(ppu_context* ctx)    { ctx->gpr[3] = 0; }
static void sys_lwcond_signal(ppu_context* ctx)     { ctx->gpr[3] = 0; }
static void sys_lwcond_signal_all(ppu_context* ctx) { ctx->gpr[3] = 0; }
static void sys_lwcond_signal_to(ppu_context* ctx)  { ctx->gpr[3] = 0; }
/* Now that the lwmutex is REAL, a no-op wait that keeps holding it deadlocks the
 * signaler. Release the paired lwmutex, wait briefly, reacquire (poll-style: the
 * guest's while(!predicate) loop re-checks; signalers stay no-ops). Handles the
 * common single (non-recursive) hold. */
static void sys_lwcond_wait(ppu_context* ctx)
{
    uint32_t lwcond  = (uint32_t)ctx->gpr[3];
    uint32_t lwmutex = vm_read32(lwcond + 0x00);
    HANDLE s = lwm_sem(lwmutex);
    if (s) {
        uint32_t own = vm_read32(lwmutex + LWM_OWNER);
        uint32_t rc  = vm_read32(lwmutex + LWM_RECUR);
        vm_write32(lwmutex + LWM_RECUR, 0);
        vm_write32(lwmutex + LWM_OWNER, 0);
        ReleaseSemaphore(s, 1, NULL);
        Sleep(1);
        WaitForSingleObject(s, INFINITE);
        vm_write32(lwmutex + LWM_OWNER, own);
        vm_write32(lwmutex + LWM_RECUR, rc ? rc : 1);
    }
    ctx->gpr[3] = 0;
}
'''
    new_block = r'''/* ASCENSION_M791_LWCOND_SIGNAL_WAIT_V1
 * The M7.90 device trace repeatedly reaches this import. A successful return
 * before a guest signal is not a valid lwcond wake and corrupts producer/consumer
 * state. Each waiter is linked only while holding the condition's host mutex, so
 * signal cannot be lost between queueing and releasing the guest lwmutex.
 */
struct AscensionLwcondWaiter {
    uint32_t thread_id;
    bool signaled;
    std::condition_variable cv;
    AscensionLwcondWaiter* next;
};

struct AscensionLwcondSlot {
    uint32_t addr;
    std::atomic<uint32_t> guest_id;
    std::mutex lock;
    AscensionLwcondWaiter* waiters;
};

static constexpr uint32_t ASC_LWCOND_SLOTS = 4096;
static AscensionLwcondSlot s_asc_lwconds[ASC_LWCOND_SLOTS] = {};
static std::mutex s_asc_lwcond_table_lock;
static std::atomic<uint32_t> s_lwcond_id{0x4C000000u};

static AscensionLwcondSlot* asc_lwcond_slot(uint32_t addr, bool create)
{
    if (!addr) return nullptr;
    std::lock_guard<std::mutex> guard(s_asc_lwcond_table_lock);
    const uint32_t start = (addr * 2654435761u) & (ASC_LWCOND_SLOTS - 1u);
    for (uint32_t i = 0; i < ASC_LWCOND_SLOTS; ++i) {
        AscensionLwcondSlot* slot = &s_asc_lwconds[(start + i) & (ASC_LWCOND_SLOTS - 1u)];
        if (slot->addr == addr) return slot;
        if (!slot->addr) {
            if (!create) return nullptr;
            slot->addr = addr;
            return slot;
        }
    }
    return nullptr;
}

static void asc_lwcond_unlink(AscensionLwcondSlot* slot, AscensionLwcondWaiter* waiter)
{
    AscensionLwcondWaiter** at = &slot->waiters;
    while (*at && *at != waiter) at = &(*at)->next;
    if (*at) *at = waiter->next;
}

static void sys_lwcond_create(ppu_context* ctx)
{
    const uint32_t lwcond = (uint32_t)ctx->gpr[3];
    const uint32_t lwmutex = (uint32_t)ctx->gpr[4];
    AscensionLwcondSlot* slot = asc_lwcond_slot(lwcond, true);
    if (!slot || !lwmutex) {
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010002u; /* CELL_EINVAL */
        return;
    }
    std::lock_guard<std::mutex> guard(slot->lock);
    if (slot->waiters) {
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x8001000Au; /* CELL_EBUSY */
        return;
    }
    const uint32_t id = s_lwcond_id.fetch_add(1, std::memory_order_relaxed) + 1u;
    vm_write32(lwcond + 0x00, lwmutex);
    vm_write32(lwcond + 0x04, id);
    slot->guest_id = id;
    ctx->gpr[3] = 0;
}

static void sys_lwcond_destroy(ppu_context* ctx)
{
    const uint32_t lwcond = (uint32_t)ctx->gpr[3];
    AscensionLwcondSlot* slot = asc_lwcond_slot(lwcond, false);
    if (!slot) { ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010003u; return; }
    std::lock_guard<std::mutex> guard(slot->lock);
    if (slot->waiters) { ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x8001000Au; return; }
    slot->guest_id = 0;
    vm_write32(lwcond + 0x04, 0);
    ctx->gpr[3] = 0;
}

static void asc_lwcond_signal(ppu_context* ctx, bool all, bool targeted)
{
    const uint32_t lwcond = (uint32_t)ctx->gpr[3];
    AscensionLwcondSlot* slot = asc_lwcond_slot(lwcond, false);
    if (!slot) {
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010003u; /* CELL_ESRCH */
        return;
    }
    const uint32_t target = (uint32_t)ctx->gpr[4];
    std::lock_guard<std::mutex> guard(slot->lock);
    if (!slot->guest_id || slot->guest_id != vm_read32(lwcond + 0x04)) {
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010003u;
        return;
    }
    bool found = false;
    for (AscensionLwcondWaiter* waiter = slot->waiters; waiter; waiter = waiter->next) {
        if (targeted && target != UINT32_MAX && waiter->thread_id != target) continue;
        waiter->signaled = true;
        waiter->cv.notify_one();
        found = true;
        if (!all) break;
    }
    (void)found; /* A signal with no waiter is successful; the guest predicate is authoritative. */
    ctx->gpr[3] = 0;
}

static void sys_lwcond_signal(ppu_context* ctx)     { asc_lwcond_signal(ctx, false, false); }
static void sys_lwcond_signal_all(ppu_context* ctx) { asc_lwcond_signal(ctx, true, false); }
static void sys_lwcond_signal_to(ppu_context* ctx)  { asc_lwcond_signal(ctx, false, true); }

static void sys_lwcond_wait(ppu_context* ctx)
{
    const uint32_t lwcond = (uint32_t)ctx->gpr[3];
    const uint64_t timeout_us = ctx->gpr[4];
    AscensionLwcondSlot* slot = asc_lwcond_slot(lwcond, false);
    if (!slot || !slot->guest_id || slot->guest_id != vm_read32(lwcond + 0x04)) {
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010003u; /* CELL_ESRCH */
        return;
    }
    const uint32_t lwmutex = vm_read32(lwcond + 0x00);
    HANDLE semaphore = lwm_sem(lwmutex);
    if (!lwmutex || !semaphore) {
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010002u; /* CELL_EINVAL */
        return;
    }

    AscensionLwcondWaiter waiter{};
    waiter.thread_id = LWM_SELF(ctx);
    std::unique_lock<std::mutex> guard(slot->lock);
    if (slot->guest_id != vm_read32(lwcond + 0x04)) {
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010003u;
        return;
    }
    waiter.next = slot->waiters;
    slot->waiters = &waiter;

    const uint32_t owner = vm_read32(lwmutex + LWM_OWNER);
    const uint32_t recur = vm_read32(lwmutex + LWM_RECUR);
    vm_write32(lwmutex + LWM_RECUR, 0);
    vm_write32(lwmutex + LWM_OWNER, 0);
    if (!ReleaseSemaphore(semaphore, 1, NULL)) {
        asc_lwcond_unlink(slot, &waiter);
        vm_write32(lwmutex + LWM_OWNER, owner);
        vm_write32(lwmutex + LWM_RECUR, recur);
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010002u;
        return;
    }

    bool signaled = false;
    if (!timeout_us || timeout_us == UINT64_MAX) {
        waiter.cv.wait(guard, [&waiter] { return waiter.signaled; });
        signaled = true;
    } else {
        const uint64_t max_us = (uint64_t)std::chrono::microseconds::max().count();
        const auto timeout = std::chrono::microseconds((int64_t)(timeout_us > max_us ? max_us : timeout_us));
        signaled = waiter.cv.wait_for(guard, timeout, [&waiter] { return waiter.signaled; });
    }
    asc_lwcond_unlink(slot, &waiter);
    guard.unlock();

    /* PS3 reacquires the associated lwmutex even when the condition times out. */
    if (WaitForSingleObject(semaphore, INFINITE) != WAIT_OBJECT_0) {
        ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80010002u;
        return;
    }
    vm_write32(lwmutex + LWM_OWNER, LWM_SELF(ctx));
    vm_write32(lwmutex + LWM_RECUR, recur ? recur : 1u);
    ctx->gpr[3] = signaled ? 0 : (uint64_t)(int64_t)(int32_t)0x8001000Bu; /* CELL_ETIMEDOUT */
}
'''
    if source.count(old_block) != 1:
        raise SystemExit("M7.91 cannot locate the pinned lwcond poll/no-op implementation")
    source = source.replace(old_block, new_block, 1)
    path.write_text(source)


def apply_ascension_gcm_park_watchdog_fix(upstream: pathlib.Path) -> None:
    """Honor Ascension's SPU-built FIFO park and semaphore waits."""
    path = upstream / "libs/video/cellGcmSys.c"
    source = path.read_text()
    marker = "ASCENSION_GCM_WAIT_STATES_NOT_STUCK_V1"
    if marker in source:
        return

    old_grace = "#define GCM_PARK_GRACE_MS 50ull"
    new_grace = '''#define GCM_PARK_GRACE_MS 50ull
/* GCM_PARK_WAIT_MS lets the title's recompiled SPU jobs finish filling and
 * patching the next command segment before the walker skips a standing park. */
static unsigned long long gcm_park_grace_ms(void)
{
    static unsigned long long ms = ~0ull;
    if (ms == ~0ull) {
        const char* e = getenv("GCM_PARK_WAIT_MS");
        ms = e ? strtoull(e, NULL, 0) : GCM_PARK_GRACE_MS;
    }
    return ms;
}'''
    if source.count(old_grace) != 1:
        raise SystemExit("M7.93 cannot locate the pinned GCM park grace")
    source = source.replace(old_grace, new_grace, 1)

    old_use = "now - park_since >= GCM_PARK_GRACE_MS"
    if source.count(old_use) != 1:
        raise SystemExit("M7.93 cannot locate the GCM park timeout")
    source = source.replace(old_use, "now - park_since >= gcm_park_grace_ms()", 1)

    old_sema = "                if (sem_blocked) break;"
    if source.count(old_sema) != 1:
        raise SystemExit("M7.93 cannot locate the blocked GCM semaphore branch")
    source = source.replace(old_sema,
                            '                if (sem_blocked) { why = "sema-acquire"; break; }', 1)

    old = '''    { static u32 last = 0xFFFFFFFFu; static int stuck = 0;
      if (s_fifo_getoff == last && s_fifo_getoff != put) {
          if (++stuck >= 8) { gcm_fifo_dump_around(s_fifo_getoff);
                             gcm_fifo_resync_why("stuck-get", &s_fifo_getoff, put); stuck = 0; }
      } else { stuck = 0; last = s_fifo_getoff; } }'''
    new = '''    /* ASCENSION_GCM_WAIT_STATES_NOT_STUCK_V1
     * A parked JUMP and a blocked hardware semaphore are expected wait states
     * in Ascension: SPU jobs patch the former and release the label for the
     * latter. Their own bounded waits govern recovery; counting either as a
     * stuck get would jump to `put` and discard unfinished game commands. */
    { static u32 last = 0xFFFFFFFFu; static int stuck = 0;
      if (why && (strcmp(why, "parked") == 0 || strcmp(why, "sema-acquire") == 0)) {
          stuck = 0; last = s_fifo_getoff;
      }
      else if (s_fifo_getoff == last && s_fifo_getoff != put) {
          if (++stuck >= 8) { gcm_fifo_dump_around(s_fifo_getoff);
                             gcm_fifo_resync_why("stuck-get", &s_fifo_getoff, put); stuck = 0; }
      } else { stuck = 0; last = s_fifo_getoff; } }'''
    if source.count(old) != 1:
        raise SystemExit("M7.93 cannot locate the GCM parked-FIFO stuck-get watchdog")
    path.write_text(source.replace(old, new, 1))


def apply_ascension_report_task_sync(upstream: pathlib.Path) -> None:
    """Port Ascension PC's bounded GET_REPORT/SPU task synchronization."""
    workload_path = upstream / "runtime/spu/spu_workload.c"
    workload = workload_path.read_text(errors="replace")
    if TASK_ACTIVITY_MARKER in workload:
        required = ("spu_taskset_tasks_running", "spu_taskset_task_ended",
                    "SPU_WAITSIG_POLL_MS", "spu_task_back_in_wait")
        if any(token not in workload for token in required):
            raise SystemExit("partial M7.98 SPU task activity patch")
    else:
        activity = r'''/* ASCENSION_M798_SPURS_TASK_ACTIVITY_V1
 * The Ascension PC runtime holds GET_REPORT while signalled SPU taskset work
 * is active. Count task threads outside WAIT_SIGNAL and include a signal that
 * is pending for a parked task, so the RSX cannot consume the next report
 * before that task starts its round. */
static volatile long s_tasks_out_of_wait;
extern void cellGcm_fifo_kick(void);
static void spu_task_back_in_wait(void)
{
    if (__atomic_sub_fetch(&s_tasks_out_of_wait, 1, __ATOMIC_ACQ_REL) == 0)
        cellGcm_fifo_kick();
}
static _Thread_local int s_task_out;
long spu_taskset_tasks_running(void)
{
    const long n = __atomic_load_n(&s_tasks_out_of_wait, __ATOMIC_ACQUIRE);
    if (n) return n;
    for (int i = 0; i < SPU_PARKED_MAX; i++) {
        const uint64_t key = s_parked[i];
        if (key && spurs_bitset_test((uint32_t)(key >> 32) + CSTS_SIGNALLED,
                                      (uint32_t)(key & 0xFFFFFFFFu) - 1u))
            return 1;
    }
    return 0;
}
void spu_taskset_task_ended(void)
{
    if (s_task_out) { s_task_out = 0; spu_task_back_in_wait(); }
}
'''
        wait_anchor = "int spu_taskset_wait_signal(uint32_t taskset_ea, uint32_t taskId)\n{\n"
        if workload.count(wait_anchor) != 1:
            raise SystemExit("M7.98 cannot locate the SPU WAIT_SIGNAL implementation")
        workload = workload.replace(wait_anchor, activity + "\n" + wait_anchor, 1)

        entry = "    if (!taskset_ea || taskId >= 128) return 0;\n"
        if workload.count(entry) != 1:
            raise SystemExit("M7.98 cannot locate WAIT_SIGNAL task entry")
        workload = workload.replace(entry, entry +
            "    if (s_task_out) { s_task_out = 0; spu_task_back_in_wait(); }\n", 1)

        wait_setup = "    unsigned secs = 0;\n    /* LBP_WS_DRAIN=<secs>:"
        if workload.count(wait_setup) != 1:
            raise SystemExit("M7.98 cannot locate WAIT_SIGNAL timeout setup")
        workload = workload.replace(wait_setup, '''    unsigned secs = 0;
    /* Match the PC port: re-check a taskset signal every 2 ms if the host
     * condition wake is missed during an SPU reservation-line commit. */
    static int wait_poll_ms = -1;
    if (wait_poll_ms < 0) {
        const char* value = getenv("SPU_WAITSIG_POLL_MS");
        wait_poll_ms = value ? atoi(value) : 2;
        if (wait_poll_ms <= 0 || wait_poll_ms > 1000) wait_poll_ms = 1000;
    }
    unsigned waited_ms = 0;
    /* LBP_WS_DRAIN=<secs>:''', 1)

        win_wait = """    while (!spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId)) {
        if (!SleepConditionVariableSRW(&s_sig_cv, &s_sig_lock, 1000, 0)) {
            static int _n = 0;"""
        win_new = """    while (!spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId)) {
        if (!SleepConditionVariableSRW(&s_sig_cv, &s_sig_lock, (DWORD)wait_poll_ms, 0)) {
            if (spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId)) break;
            if ((waited_ms += (unsigned)wait_poll_ms) < 1000) continue;
            waited_ms = 0;
            static int _n = 0;"""
        if workload.count(win_wait) != 1:
            raise SystemExit("M7.98 cannot patch Windows WAIT_SIGNAL polling")
        workload = workload.replace(win_wait, win_new, 1)

        posix_wait = """    while (!spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId)) {
        struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts); ts.tv_sec += 1;
        if (pthread_cond_timedwait(&s_sig_cv, &s_sig_lock, &ts) != 0) {
            static int _n = 0;"""
        posix_new = """    while (!spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId)) {
        struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_nsec += (long)wait_poll_ms * 1000000L;
        while (ts.tv_nsec >= 1000000000L) { ts.tv_nsec -= 1000000000L; ts.tv_sec++; }
        if (pthread_cond_timedwait(&s_sig_cv, &s_sig_lock, &ts) != 0) {
            if (spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId)) break;
            if ((waited_ms += (unsigned)wait_poll_ms) < 1000) continue;
            waited_ms = 0;
            static int _n = 0;"""
        if workload.count(posix_wait) != 1:
            raise SystemExit("M7.98 cannot patch POSIX WAIT_SIGNAL polling")
        workload = workload.replace(posix_wait, posix_new, 1)

        count_before_clear = """    if (!drained) spurs_bitset_clear(taskset_ea + CSTS_SIGNALLED, taskId);"""
        active_before_clear = """    if (!s_task_out) {
        s_task_out = 1;
        __atomic_fetch_add(&s_tasks_out_of_wait, 1, __ATOMIC_ACQ_REL);
    }
    if (!drained) spurs_bitset_clear(taskset_ea + CSTS_SIGNALLED, taskId);"""
        if workload.count(count_before_clear) != 2:
            raise SystemExit("M7.98 cannot locate both WAIT_SIGNAL signal-clear paths")
        workload = workload.replace(count_before_clear, active_before_clear, 2)

        resume = """    spu_serial_acquire();       /* resume: re-take the serial lock */
    { extern unsigned long long ps3_ms_now(void);"""
        resume_new = """    spu_serial_acquire();       /* resume: re-take the serial lock */
    if (!s_task_out) {
        s_task_out = 1;
        __atomic_fetch_add(&s_tasks_out_of_wait, 1, __ATOMIC_ACQ_REL);
    }
    { extern unsigned long long ps3_ms_now(void);"""
        if workload.count(resume) != 1:
            raise SystemExit("M7.98 cannot locate WAIT_SIGNAL resume")
        workload = workload.replace(resume, resume_new, 1)

        exited = "static void spu_taskset_task_exited(uint32_t taskset_ea, uint32_t done_task)\n{\n"
        if workload.count(exited) != 1:
            raise SystemExit("M7.98 cannot locate async task exit")
        workload = workload.replace(exited, "extern void spu_taskset_task_ended(void);\n\n" + exited +
            "    spu_taskset_task_ended();\n", 1)
        workload_path.write_text(workload)

    gcm_path = upstream / "libs/video/cellGcmSys.c"
    gcm = gcm_path.read_text(errors="replace")
    if REPORT_HOLD_MARKER in gcm:
        if 'why = "report-hold"' not in gcm or '"report-hold")' not in gcm:
            raise SystemExit("partial M7.98 RSX report hold patch")
        return

    kick_anchor = """void cellGcm_fifo_kick_wait(unsigned ms)
{
    static int on = -1;
    if (on < 0) { const char* e = getenv("GCM_FIFO_KICK"); on = (e && *e == '0') ? 0 : 1; }
    HANDLE ev = on ? (HANDLE)cellGcm_fifo_kick_event() : NULL;
    if (ev) WaitForSingleObject(ev, ms);
    else    Sleep(ms);
}
"""
    kick_new = kick_anchor + """
/* Wake the present-thread walker after the last active SPU task re-enters
 * WAIT_SIGNAL and releases its report hold. */
void cellGcm_fifo_kick(void)
{
    if (s_gcm_kick_ev) SetEvent(s_gcm_kick_ev);
}
"""
    if gcm.count(kick_anchor) != 1:
        raise SystemExit("M7.98 cannot locate the GCM present-thread kick event")
    gcm = gcm.replace(kick_anchor, kick_new, 1)

    method_anchor = """            for (u32 i = 0; i < count; i++) {
                u32 dea = gcm_io2ea(s_fifo_getoff + 4 + i * 4);
                if (!dea) break;
                u32 m = (type == 0) ? method + i * 4 : method;
                /* GCM_SET_USER_COMMAND"""
    method_new = """            /* ASCENSION_M798_GCM_REPORT_SPU_HOLD_V1
             * Ascension RsxSync uses GET_REPORT to release taskset work. The
             * PC port bounds the next report until signalled SPU tasks finish
             * or 50 ms elapse; otherwise the guest can signal the next round
             * while the previous one is still in its barriers. */
            if (subch == 0 && (type == 0 ?
                    (method <= 0x1800u && 0x1800u < method + count * 4u) :
                     method == 0x1800u)) {
                static long report_hold_ms = -1;
                static unsigned long long report_hold_since;
                if (report_hold_ms < 0) {
                    const char* value = getenv("GCM_REPORT_SPU_HOLD_MS");
                    report_hold_ms = value ? atol(value) : 0;
                }
                extern long spu_taskset_tasks_running(void) __attribute__((weak));
                if (report_hold_ms > 0) {
                    /* ZPASS (type 1) reports do not signal tasksets. Ascension
                     * emits many per frame; holding them starves the RSX. */
                    static int report_hold_all = -1;
                    if (report_hold_all < 0)
                        report_hold_all = getenv("GCM_REPORT_HOLD_ALL") ? 1 : 0;
                    u32 report_type = 0;
                    {
                        const u32 index = type == 0 ? (0x1800u - method) / 4u : 0u;
                        const u32 report_ea = gcm_io2ea(s_fifo_getoff + 4 + index * 4);
                        if (report_ea) report_type = vm_read32(report_ea) >> 24;
                    }
                    if (report_hold_all || report_type != 1) {
                        const unsigned long long now = ps3_qpc_us();
                        if (spu_taskset_tasks_running && spu_taskset_tasks_running() > 0) {
                            if (!report_hold_since) report_hold_since = now;
                            if (now - report_hold_since <
                                    (unsigned long long)report_hold_ms * 1000ull) {
                                why = "report-hold";
                                break;
                            }
                        }
                        report_hold_since = 0;
                    }
                }
            }
            for (u32 i = 0; i < count; i++) {
                u32 dea = gcm_io2ea(s_fifo_getoff + 4 + i * 4);
                if (!dea) break;
                u32 m = (type == 0) ? method + i * 4 : method;
                /* GCM_SET_USER_COMMAND"""
    if gcm.count(method_anchor) != 1:
        raise SystemExit("M7.98 cannot locate NV4097 FIFO method dispatch")
    gcm = gcm.replace(method_anchor, method_new, 1)

    watchdog_old = '''      if (why && (strcmp(why, "parked") == 0 || strcmp(why, "sema-acquire") == 0)) {'''
    watchdog_new = '''      if (why && (strcmp(why, "parked") == 0 || strcmp(why, "sema-acquire") == 0 ||
                  strcmp(why, "report-hold") == 0)) {'''
    if gcm.count(watchdog_old) != 1:
        raise SystemExit("M7.98 cannot locate GCM non-stuck wait classification")
    gcm = gcm.replace(watchdog_old, watchdog_new, 1)
    gcm_path.write_text(gcm)


def apply_ascension_gcm_park_spu_hold(upstream: pathlib.Path) -> None:
    """Hold a patched RSX park until the SPU round that feeds it is complete.

    The Ascension PC port's patch 0017 documents a first-frame race: the host
    FIFO can reach the next segment before signalled SPU taskset work finishes
    the prior round. The next task signals are then consumed by tasks still in
    their old barriers. Keep the same bounded 50 ms handoff on iOS and expose
    whether it held, released, or timed out in the live report.
    """
    path = upstream / "libs/video/cellGcmSys.c"
    source = path.read_text(errors="replace")
    if PARK_SPU_HOLD_MARKER in source:
        required = (
            "s_last_park_off = s_fifo_getoff",
            "if (s_fifo_getoff == s_last_park_off)",
            'getenv("GCM_PARK_SPU_HOLD_MS")',
            "spu_taskset_tasks_running()",
            "s_asc_park_spu_hold_since",
            'why = "spu-hold"',
            'strcmp(why, "spu-hold") == 0',
            "cellGcmResetAscensionParkHoldMetrics",
            "cellGcmCopyAscensionParkHoldMetrics",
        )
        missing = [token for token in required if token not in source]
        if missing:
            raise SystemExit(f"partial M8.03 GCM park/SPU hold patch: {missing}")
        return

    state_anchor = "static u32 s_fifo_getoff;   /* tentative: defined below */\n"
    state = state_anchor + '''
/* ASCENSION_M803_GCM_PARK_SPU_HOLD_V1
 * The first patched jump after a park starts the next FIFO segment. Hold it
 * briefly while the SPU task round that fills that segment is still active. */
static u32 s_last_park_off = ~0u;
static long s_asc_park_spu_hold_ms = -1;
static unsigned long long s_asc_park_spu_hold_since;
static int s_asc_park_spu_held_for_task;
static unsigned long long s_asc_park_spu_hold_metrics[3];
void cellGcmResetAscensionParkHoldMetrics(void)
{
    s_last_park_off = ~0u;
    s_asc_park_spu_hold_ms = -1;
    s_asc_park_spu_hold_since = 0;
    s_asc_park_spu_held_for_task = 0;
    for (unsigned i = 0; i < 3; ++i)
        __atomic_store_n(&s_asc_park_spu_hold_metrics[i], 0, __ATOMIC_RELAXED);
}
void cellGcmCopyAscensionParkHoldMetrics(unsigned long long out[3])
{
    if (!out) return;
    for (unsigned i = 0; i < 3; ++i)
        out[i] = __atomic_load_n(&s_asc_park_spu_hold_metrics[i], __ATOMIC_RELAXED);
}
'''
    if source.count(state_anchor) != 1:
        raise SystemExit("M8.03 cannot locate the GCM FIFO get-position declaration")
    source = source.replace(state_anchor, state, 1)

    park_anchor = '''                  why = "parked";
                  break;'''
    park_new = '''                  /* Remember the exact park. When its self-JUMP is patched,
                   * the first drain of the new segment may have to wait for
                   * the SPU tasks that produce its draw data. */
                  s_last_park_off = s_fifo_getoff;
                  why = "parked";
                  break;'''
    if source.count(park_anchor) != 1:
        raise SystemExit("M8.03 cannot locate the GCM self-JUMP park branch")
    source = source.replace(park_anchor, park_new, 1)

    advance_anchor = '''              }
              s_fifo_getoff = tgt; }
            continue;
        }
        if ((w & 3) == 2) {                    /* CALL: offset | 2 */'''
    advance_new = '''              }
              /* GCM_PARK_SPU_HOLD_MS=<ms>: a patched park starts the next
               * segment. The PC port found that a no-cost RSX can overtake
               * the signalled SPU task round that fills it. */
              if (s_fifo_getoff == s_last_park_off) {
                  if (s_asc_park_spu_hold_ms < 0) {
                      const char* value = getenv("GCM_PARK_SPU_HOLD_MS");
                      s_asc_park_spu_hold_ms = value ? atol(value) : 0;
                  }
                  extern long spu_taskset_tasks_running(void) __attribute__((weak));
                  const long active = spu_taskset_tasks_running
                      ? spu_taskset_tasks_running() : 0;
                  if (s_asc_park_spu_hold_ms > 0 && active > 0) {
                      extern unsigned long long ps3_ms_now(void);
                      const unsigned long long now = ps3_ms_now();
                      if (!s_asc_park_spu_hold_since) {
                          s_asc_park_spu_hold_since = now;
                          s_asc_park_spu_held_for_task = 1;
                      }
                      if (now - s_asc_park_spu_hold_since <
                              (unsigned long long)s_asc_park_spu_hold_ms) {
                          __atomic_add_fetch(&s_asc_park_spu_hold_metrics[0], 1,
                                             __ATOMIC_RELAXED);
                          why = "spu-hold";
                          break;
                      }
                      if (s_asc_park_spu_held_for_task)
                          __atomic_add_fetch(&s_asc_park_spu_hold_metrics[2], 1,
                                             __ATOMIC_RELAXED);
                  } else if (s_asc_park_spu_held_for_task) {
                      __atomic_add_fetch(&s_asc_park_spu_hold_metrics[1], 1,
                                         __ATOMIC_RELAXED);
                  }
                  s_asc_park_spu_hold_since = 0;
                  s_asc_park_spu_held_for_task = 0;
                  s_last_park_off = ~0u;
              }
              s_fifo_getoff = tgt; }
            continue;
        }
        if ((w & 3) == 2) {                    /* CALL: offset | 2 */'''
    if source.count(advance_anchor) != 1:
        raise SystemExit("M8.03 cannot locate the GCM JUMP target advance")
    source = source.replace(advance_anchor, advance_new, 1)

    watchdog_anchor = '''strcmp(why, "report-hold") == 0)) {'''
    watchdog_new = '''strcmp(why, "report-hold") == 0 ||
                  strcmp(why, "spu-hold") == 0)) {'''
    if source.count(watchdog_anchor) != 1:
        raise SystemExit("M8.03 cannot locate GCM expected-wait classification")
    source = source.replace(watchdog_anchor, watchdog_new, 1)
    path.write_text(source)


def apply_ascension_spurs_report_wake(upstream: pathlib.Path) -> None:
    """Wake idle/backed-off SPURS WWS workers when the RSX writes a report."""
    spurs_path = upstream / "libs/spurs/cellSpurs.c"
    gcm_path = upstream / "libs/video/cellGcmSys.c"
    spurs = spurs_path.read_text(errors="replace")
    gcm = gcm_path.read_text(errors="replace")
    if SPURS_REPORT_WAKE_MARKER in spurs or SPURS_REPORT_WAKE_MARKER in gcm:
        required = (
            "spurs_external_event(void)", "s_asc_gpu_report_events",
            "out[8]=__atomic_load_n(&s_asc_gpu_report_events",
            "out[9]=__atomic_load_n(&s_asc_gpu_report_wakes",
        )
        if any(token not in spurs for token in required) or \
                "spurs_external_event();" not in gcm:
            raise SystemExit("partial M8.04 SPURS GPU-report wake patch")
        return

    metric_anchor = "static volatile u64 s_asc_pm_found, s_asc_pm_missing, s_asc_last_dispatch_wid;\n"
    if spurs.count(metric_anchor) != 1:
        raise SystemExit("M8.04 cannot locate the 32-workload SPURS metrics")
    spurs = spurs.replace(
        metric_anchor,
        metric_anchor +
        "static volatile u64 s_asc_gpu_report_events, s_asc_gpu_report_wakes;\n",
        1,
    )

    reset_anchor = "    __atomic_store_n(&s_asc_last_dispatch_wid, UINT64_MAX, __ATOMIC_RELAXED);\n"
    if spurs.count(reset_anchor) != 1:
        raise SystemExit("M8.04 cannot locate the SPURS metrics reset")
    spurs = spurs.replace(
        reset_anchor,
        reset_anchor +
        "    __atomic_store_n(&s_asc_gpu_report_events, 0, __ATOMIC_RELAXED);\n"
        "    __atomic_store_n(&s_asc_gpu_report_wakes, 0, __ATOMIC_RELAXED);\n",
        1,
    )

    copy_signature = "void cellSpursCopyAscensionMetrics(u64 out[8]) {"
    if spurs.count(copy_signature) != 1:
        raise SystemExit("M8.04 cannot locate the SPURS metrics copy API")
    spurs = spurs.replace(copy_signature,
                          "void cellSpursCopyAscensionMetrics(u64 out[10]) {", 1)
    copy_anchor = "    out[7]=__atomic_load_n(&s_asc_last_dispatch_wid,__ATOMIC_RELAXED);\n"
    if spurs.count(copy_anchor) != 1:
        raise SystemExit("M8.04 cannot extend the SPURS metrics copy API")
    spurs = spurs.replace(
        copy_anchor,
        copy_anchor +
        "    out[8]=__atomic_load_n(&s_asc_gpu_report_events,__ATOMIC_RELAXED);\n"
        "    out[9]=__atomic_load_n(&s_asc_gpu_report_wakes,__ATOMIC_RELAXED);\n",
        1,
    )

    helper_anchor = (
        "static void wkl_curcont_set(u32 ea, u32 wid, u8 v)\n"
        "{ if (wid < 16) vm_base[ea + SPURS_WKL_CURCONT + wid] = v; }\n"
    )
    helper = f'''\n/* {SPURS_REPORT_WAKE_MARKER}
 * A GET_REPORT is an external event for WWS jobs parked at RsxBarrier. It
 * changes no readyCount/signal bit, so clear scheduler idle back-off and wake
 * the coordinator without taking its lock (the RSX may be under FIFO lock). */
void spurs_external_event(void)
{{
    __atomic_add_fetch(&s_asc_gpu_report_events, 1, __ATOMIC_RELAXED);
    for (int i = 0; i < MAX_SPURS_INST; ++i) {{
        struct SpursInst* si = &s_inst[i];
        if (!__atomic_load_n(&si->ea, __ATOMIC_ACQUIRE)) continue;
        for (u32 wid = 0; wid < SPURS_MAX_WID; ++wid)
            __atomic_store_n(&si->idle[wid], (u8)0, __ATOMIC_RELAXED);
        __atomic_add_fetch(&s_asc_gpu_report_wakes, 1, __ATOMIC_RELAXED);
        WakeAllConditionVariable(&si->wake);
    }}
}}
'''
    if spurs.count(helper_anchor) != 1:
        raise SystemExit("M8.04 cannot place the SPURS external-report event")
    spurs = spurs.replace(helper_anchor, helper_anchor + helper, 1)

    report_anchor = "                            s_report_data[idx].value = val;\n"
    if gcm.count(report_anchor) != 1:
        raise SystemExit("M8.04 cannot locate the guest GCM report write")
    gcm = gcm.replace(
        report_anchor,
        report_anchor +
        "                            /* M8.04: wake WWS RsxBarrier polling on report. */\n"
        "                            { extern void spurs_external_event(void); spurs_external_event(); }\n",
        1,
    )
    spurs_path.write_text(spurs)
    gcm_path.write_text(gcm)


def apply_ascension_spu_stack_metrics(upstream: pathlib.Path) -> None:
    """Retry SPU worker creation with large-but-bounded stacks before default."""
    path = upstream / "runtime/spu/spu_workload.c"
    source = path.read_text(errors="replace")
    if STACK_METRICS_MARKER in source:
        required = ("spu_workload_reset_ascension_stack_metrics",
                    "spu_workload_copy_ascension_stack_metrics",
                    "stack_sizes[4] = {256u << 20, 64u << 20, 32u << 20, 16u << 20}",
                    "s_asc_worker_stack_metrics[16]")
        missing = [token for token in required if token not in source]
        if missing:
            raise SystemExit(f"partial M8.04 SPU stack recovery patch: {missing}")
        return

    thread_anchor = "#ifdef _WIN32\nstatic DWORD WINAPI spu_async_thread"
    metrics = '''/* ASCENSION_M803_SPU_STACK_METRICS_V1
 * GoW II's macOS port found deep lifted SPU call chains can exceed Darwin's
 * 512 KiB default; the pinned runtime notes even 1 MiB can overflow a Bink
 * path. M8.04 retries descending bounded reservations before using default. */
/* ASCENSION_M804_SPU_STACK_RECOVERY_V1 */
static unsigned long long s_asc_worker_stack_metrics[17];
void spu_workload_reset_ascension_stack_metrics(void)
{
    for (unsigned i = 0; i < 17; ++i)
        __atomic_store_n(&s_asc_worker_stack_metrics[i], 0, __ATOMIC_RELAXED);
}
void spu_workload_copy_ascension_stack_metrics(unsigned long long out[17])
{
    if (!out) return;
    for (unsigned i = 0; i < 17; ++i)
        out[i] = __atomic_load_n(&s_asc_worker_stack_metrics[i], __ATOMIC_RELAXED);
}

'''
    if source.count(thread_anchor) != 1:
        raise SystemExit("M8.03 cannot locate the SPU async thread wrappers")
    source = source.replace(thread_anchor, metrics + thread_anchor, 1)

    stack_anchor = '''    int prc = EINVAL;
    if (pthread_attr_setstacksize(&attr, 256u << 20) == 0)
        prc = pthread_create(&th, &attr, spu_async_thread, j);
    pthread_attr_destroy(&attr);'''
    stack_new = '''    __atomic_add_fetch(&s_asc_worker_stack_metrics[0], 1, __ATOMIC_RELAXED);
    const size_t stack_sizes[4] = {256u << 20, 64u << 20, 32u << 20, 16u << 20};
    const unsigned attr_metrics[4] = {1, 4, 7, 10};
    const unsigned success_metrics[4] = {2, 5, 8, 11};
    const unsigned failure_metrics[4] = {3, 6, 9, 12};
    int created = 0;
    int prc = 0;
    for (unsigned i = 0; i < 4; ++i) {
        const int arc = pthread_attr_setstacksize(&attr, stack_sizes[i]);
        if (arc != 0) {
            __atomic_store_n(&s_asc_worker_stack_metrics[16],
                             (unsigned long long)arc, __ATOMIC_RELAXED);
            prc = arc;
            continue;
        }
        __atomic_add_fetch(&s_asc_worker_stack_metrics[attr_metrics[i]],
                           1, __ATOMIC_RELAXED);
        prc = pthread_create(&th, &attr, spu_async_thread, j);
        if (prc == 0) {
            __atomic_add_fetch(&s_asc_worker_stack_metrics[success_metrics[i]],
                               1, __ATOMIC_RELAXED);
            created = 1;
            break;
        }
        __atomic_add_fetch(&s_asc_worker_stack_metrics[failure_metrics[i]],
                           1, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_worker_stack_metrics[15],
                         (unsigned long long)prc, __ATOMIC_RELAXED);
    }
    pthread_attr_destroy(&attr);'''
    if source.count(stack_anchor) != 1:
        raise SystemExit("M8.04 cannot locate the POSIX SPU worker stack request")
    source = source.replace(stack_anchor, stack_new, 1)

    fallback_anchor = '''    if (prc != 0)
        prc = pthread_create(&th, NULL, spu_async_thread, j);'''
    fallback_new = '''    if (!created) {
        __atomic_add_fetch(&s_asc_worker_stack_metrics[13], 1, __ATOMIC_RELAXED);
        prc = pthread_create(&th, NULL, spu_async_thread, j);
        if (prc == 0) {
            __atomic_add_fetch(&s_asc_worker_stack_metrics[14], 1, __ATOMIC_RELAXED);
            created = 1;
        } else {
            __atomic_store_n(&s_asc_worker_stack_metrics[15],
                             (unsigned long long)prc, __ATOMIC_RELAXED);
        }
    }'''
    if source.count(fallback_anchor) != 1:
        raise SystemExit("M8.04 cannot locate the POSIX default-stack fallback")
    path.write_text(source.replace(fallback_anchor, fallback_new, 1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upstream", type=pathlib.Path, required=True)
    ap.add_argument("--repo", type=pathlib.Path, default=pathlib.Path("."))
    args = ap.parse_args()
    upstream = args.upstream.resolve()
    repo = args.repo.resolve()
    actual = run(["git", "-C", str(upstream), "rev-parse", "HEAD"], capture=True).strip()
    if actual != PIN:
        raise SystemExit(f"M7.83 PS3Recomp source pin mismatch: {actual} != {PIN}")

    patch_dir = repo / "patches/ps3recomp"
    spurs_c = upstream / "libs/spurs/cellSpurs.c"
    workload = upstream / "runtime/spu/spu_workload.c"
    sys_event = upstream / "runtime/syscalls/sys_event.c"
    gcm_source = upstream / "libs/video/cellGcmSys.c"
    patch_assets = [
        ("ps3recomp-0005-gcm-offset-table.patch",
         ((gcm_source, "s_offset_tables_published"),
          (gcm_source, "offset_table_write_through"),
          (gcm_source, "s_offset_tables_published = 1;"))),
        ("ps3recomp-0001-spurs2.patch", ((spurs_c, "cellSpursInitializeWithAttribute2"),)),
        ("ps3recomp-0003-lfqueue-push.patch", ((spurs_c, "_cellSpursLFQueuePushBody"), (workload, "spu_signal_parked_on_line"))),
        ("ps3recomp-0019-spurs-taskset2-task-starts.patch", ((workload, "spu_taskset_set_running"), (sys_event, "sys_event_flag_create_host"))),
    ]
    for filename, markers in patch_assets:
        apply_patch(upstream, patch_dir / filename, markers)
    apply_api_layer(upstream, repo)
    spurs_source = upstream / "libs/spurs/cellSpurs.c"
    policy_source = upstream / "runtime/spu/spurs_policy.c"
    apply_patch(upstream, patch_dir / "ps3recomp-0020-spurs2-32-workloads.patch",
                ((spurs_source, WORKLOADS_MARKER), (policy_source, WORKLOADS_MARKER)),
                zero_context=True)
    apply_taskset_context_workload_id(upstream)
    apply_pm_resolution_diagnostics(upstream)
    apply_requested_pm_capture(upstream)
    apply_ascension_wws_policy(upstream)
    apply_ascension_workload_flag_scheduler(upstream)
    apply_job_dispatch_metrics(upstream)
    apply_dynamic_wws_pm_role(upstream)
    apply_lwcond_wait_signal_semantics(upstream)
    apply_ascension_gcm_park_watchdog_fix(upstream)
    apply_ascension_report_task_sync(upstream)
    apply_ascension_spurs_report_wake(upstream)
    apply_ascension_spu_stack_metrics(upstream)
    apply_ascension_gcm_park_spu_hold(upstream)
    apply_m801_taskset_runtime(upstream)

    required = {
        "libs/spurs/cellSpurs.c": (
            WORKLOADS_MARKER, "SPURS_MAX_WID 32", "SPURS_WKL_INFO2",
            "spurs_workload_limit", "cellSpursResetAscensionMetrics",
            "cellSpursCopyAscensionMetrics", "s_asc_dispatches_hi",
            PM_DIAGNOSTICS_MARKER, "cellSpursCopyAscensionPmDiagnostics",
            "s_asc_pm_diag", "spurs_guest_range_valid(pm_ea, w->sizePm)",
            PM_CAPTURE_MARKER, "cellSpursCaptureAscensionPmMiss",
            ASCENSION_POLICY_MARKER, "spurs_poll_select", "spurs_ready_level()",
            WORKLOAD_FLAG_MARKER, "SPURS_WKL_FLAG_VAL = 0x6C",
            "SPURS_WKL_FLAG_RCV = 0x77", "spurs_workload_flag_take(ea, wid)",
            "cellSpursInitializeWithAttribute2", "cellSpursCreateTaskset2",
            "_cellSpursTasksetAttribute2Initialize", "cellSpursCreateTask2",
            "cellSpursJoinTask2", "cellSpursTryJoinTask2",
            "cellSpursTasksetGetSpursAddress", "_cellSpursLFQueuePushBody",
            "cellSpursGetWorkloadFlag", "_cellSpursWorkloadFlagReceiver",
            LFQUEUE_MARKER, SPURS_REPORT_WAKE_MARKER,
            "spurs_external_event(void)",
            "out[8]=__atomic_load_n(&s_asc_gpu_report_events",
            "out[9]=__atomic_load_n(&s_asc_gpu_report_wakes",
            "ASCENSION_M772_EDGE_ZLIB_HLE_V2", MARKER),
        "libs/spurs/cellSpurs.h": ("cellSpursCreateTask2", "cellSpursJoinTask2",
                                   "cellSpursTasksetGetSpursAddress", "_cellSpursLFQueuePushBody",
                                   "cellSpursGetWorkloadFlag", "_cellSpursWorkloadFlagReceiver"),
        "libs/spurs/spurs_taskset.h": (TASKSET_LOCK_MARKER,
                                        "spurs_bitset_rmw(uint32_t bitset_ea, uint32_t taskId, int set)",
                                        "spu_lockline_lock()", "spu_coh_notify_write(word_ea)"),
        "libs/spurs/spurs_pm.c": (TASKSET_WID_MARKER,
                                  "LS_BE32(0x1DC, vm_read32(taskset_ea + CSTS_WID));"),
        "runtime/spu/spu_workload.c": ("spu_taskset_set_running", "spu_taskset_track",
                                       "spu_signal_parked_on_line", JOB_METRICS_MARKER,
                                       "spu_workload_copy_ascension_job_metrics",
                                       DYNAMIC_WWS_PM_MARKER,
                                       "spu_workload_note_wws_role(image_id, name);",
                                       TASK_ACTIVITY_MARKER,
                                       "spu_taskset_tasks_running(void)",
                                       "spu_taskset_task_ended(void)",
                                       STACK_METRICS_MARKER,
                                       "stack_sizes[4] = {256u << 20, 64u << 20, 32u << 20, 16u << 20}",
                                       "spu_workload_reset_ascension_stack_metrics",
                                       "spu_workload_copy_ascension_stack_metrics",
                                       "s_asc_worker_stack_metrics[16]",
                                       TASKSET_LOCK_MARKER, TASKSET_METRICS_MARKER,
                                       "ts_bits_clear(taskset_ea + 0x30 + done_task / 8, m)",
                                       "spu_workload_copy_ascension_taskset_metrics",
                                       "asc_taskset_add(7, 1)"),
        "runtime/spu/spu_channels.c": (DYNAMIC_WWS_PM_MARKER,
                                       "spu_workload_is_wws_pm_image(ctx->image_id)"),
        "runtime/spu/spu_dma.h": (DYNAMIC_WWS_PM_MARKER,
                                  "spu_workload_is_wws_pm_image(spu->image_id)"),
        "runtime/ppu/ppu_sysprx.cpp": (LWCOND_SEMANTICS_MARKER,
                                        "waiter.cv.wait(guard", "wait_for(guard",
                                        "asc_lwcond_signal(ctx, true, false)"),
        "runtime/syscalls/sys_event.c": ("sys_event_flag_create_host",),
        "libs/codec/edge_inflate.cpp": ("extern \"C\" int edge_inflate", "const int FULL = -2;"),
        "libs/video/cellGcmSys.c": ("s_offset_tables_published",
                                    "offset_table_write_through",
                                    "s_offset_tables_published = 1;",
                                    "ASCENSION_GCM_WAIT_STATES_NOT_STUCK_V1",
                                    "GCM_PARK_WAIT_MS", "gcm_park_grace_ms()",
                                    'why = "sema-acquire"',
                                    'strcmp(why, "sema-acquire") == 0',
                                    REPORT_HOLD_MARKER, 'why = "report-hold"',
                                    'strcmp(why, "report-hold") == 0',
                                    PARK_SPU_HOLD_MARKER,
                                    'getenv("GCM_PARK_SPU_HOLD_MS")',
                                    "spu_taskset_tasks_running()",
                                    'why = "spu-hold"',
                                    'strcmp(why, "spu-hold") == 0',
                                    "cellGcmCopyAscensionParkHoldMetrics",
                                    "spurs_external_event();"),
    }
    for filename, needles in required.items():
        text = (upstream / filename).read_text(errors="replace")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            raise SystemExit(f"M7.83 PS3Recomp SPURS2 patch incomplete in {filename}: {missing}")
    print("M8.05 applies Ascension GCM offset-table write-through, SPURS GPU-report wake, and bounded SPU worker-stack recovery")
    return 0


if __name__ == "__main__":
    sys.exit(main())
