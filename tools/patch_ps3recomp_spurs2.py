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
import subprocess
import sys


PIN = "39a36296511c445707adabcd312f0b740cfbd694"
MARKER = "ASCENSION_M772_SPURS2_TASK_API_V2"
WORKLOADS_MARKER = "ASCENSION_M772_SPURS2_WORKLOADS_32_V1"
LFQUEUE_MARKER = "ASCENSION_M772_LFQUEUE_SDK_LAYOUT_V1"
PM_DIAGNOSTICS_MARKER = "ASCENSION_M785_SPURS_PM_DIAGNOSTICS_V1"
ASCENSION_POLICY_MARKER = "ASCENSION_M786_WWS_TEMPA_READY_LEVEL_V1"
JOB_METRICS_MARKER = "ASCENSION_M787_SPURS_JOB_METRICS_V1"
PM_CAPTURE_MARKER = "ASCENSION_M788_CAPTURE_REQUESTED_PM_V1"


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
    const u32 receiver_ea = spurs_ea + 0x77u;
    const u8 receiver = vm_base[receiver_ea];
    s32 rc = CELL_OK;
    if (is_set && receiver != 0xFFu) rc = CELL_SPURS_CORE_ERROR_BUSY;
    else if (!is_set && receiver != (u8)wid) rc = CELL_SPURS_CORE_ERROR_PERM;
    else {
        /* The SDK resets the workload flag to all ones on every ownership
         * change; its receiver is the low byte of that BE flag structure. */
        vm_base[spurs_ea + 0x6Cu] = 0xFFu;
        vm_base[spurs_ea + 0x6Du] = 0xFFu;
        vm_base[spurs_ea + 0x6Eu] = 0xFFu;
        vm_base[spurs_ea + 0x6Fu] = 0xFFu;
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
    channels = channels.replace("/* SPURS kernel services (policy-module runs only):", "/* ASCENSION_M786_WWS_TEMPA_READY_LEVEL_V1 */\n    /* SPURS kernel services (policy-module runs only):", 1)
    channels_path.write_text(channels)


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
    patch_assets = [
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
    apply_pm_resolution_diagnostics(upstream)
    apply_requested_pm_capture(upstream)
    apply_ascension_wws_policy(upstream)
    apply_job_dispatch_metrics(upstream)

    required = {
        "libs/spurs/cellSpurs.c": (
            WORKLOADS_MARKER, "SPURS_MAX_WID 32", "SPURS_WKL_INFO2",
            "spurs_workload_limit", "cellSpursResetAscensionMetrics",
            "cellSpursCopyAscensionMetrics", "s_asc_dispatches_hi",
            PM_DIAGNOSTICS_MARKER, "cellSpursCopyAscensionPmDiagnostics",
            "s_asc_pm_diag", "spurs_guest_range_valid(pm_ea, w->sizePm)",
            PM_CAPTURE_MARKER, "cellSpursCaptureAscensionPmMiss",
            ASCENSION_POLICY_MARKER, "spurs_poll_select", "spurs_ready_level()",
            "cellSpursInitializeWithAttribute2", "cellSpursCreateTaskset2",
            "_cellSpursTasksetAttribute2Initialize", "cellSpursCreateTask2",
            "cellSpursJoinTask2", "cellSpursTryJoinTask2",
            "cellSpursTasksetGetSpursAddress", "_cellSpursLFQueuePushBody",
            "cellSpursGetWorkloadFlag", "_cellSpursWorkloadFlagReceiver",
            LFQUEUE_MARKER,
            "ASCENSION_M772_EDGE_ZLIB_HLE_V2", MARKER),
        "libs/spurs/cellSpurs.h": ("cellSpursCreateTask2", "cellSpursJoinTask2",
                                   "cellSpursTasksetGetSpursAddress", "_cellSpursLFQueuePushBody",
                                   "cellSpursGetWorkloadFlag", "_cellSpursWorkloadFlagReceiver"),
        "runtime/spu/spu_workload.c": ("spu_taskset_set_running", "spu_taskset_track",
                                       "spu_signal_parked_on_line", JOB_METRICS_MARKER,
                                       "spu_workload_copy_ascension_job_metrics"),
        "runtime/syscalls/sys_event.c": ("sys_event_flag_create_host",),
        "libs/codec/edge_inflate.cpp": ("extern \"C\" int edge_inflate", "const int FULL = -2;"),
    }
    for filename, needles in required.items():
        text = (upstream / filename).read_text(errors="replace")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            raise SystemExit(f"M7.83 PS3Recomp SPURS2 patch incomplete in {filename}: {missing}")
    print("M7.88 applied fail-closed WWS PM association, requested PM capture, SPURS2 scheduler, Ascension policy, job metrics, taskset, LFQueue, and Edge Zlib HLE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
