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

    required = {
        "libs/spurs/cellSpurs.c": (
            WORKLOADS_MARKER, "SPURS_MAX_WID 32", "SPURS_WKL_INFO2",
            "spurs_workload_limit", "cellSpursResetAscensionMetrics",
            "cellSpursCopyAscensionMetrics", "s_asc_dispatches_hi",
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
                                       "spu_signal_parked_on_line"),
        "runtime/syscalls/sys_event.c": ("sys_event_flag_create_host",),
        "libs/codec/edge_inflate.cpp": ("extern \"C\" int edge_inflate", "const int FULL = -2;"),
    }
    for filename, needles in required.items():
        text = (upstream / filename).read_text(errors="replace")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            raise SystemExit(f"M7.83 PS3Recomp SPURS2 patch incomplete in {filename}: {missing}")
    print("M7.83 applied 32-workload SPURS2 scheduler, live dispatch telemetry, taskset, LFQueue, and Edge Zlib HLE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
