#!/usr/bin/env python3
"""M8.14: fail closed when CellSpursTaskset2 event flags are not valid."""
from pathlib import Path
import argparse

MARK = "ASCENSION_M814_TASKSET2_EVENTFLAGS_CHECK_V1"

def replace_once(s, old, new, label):
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"M8.14 {label}: expected one anchor, found {n}")
    return s.replace(old, new, 1)

def apply(root):
    root = Path(root)
    spurs = root / "libs/spurs/cellSpurs.c"
    s = spurs.read_text()
    if MARK not in s:
        old = """        extern int64_t sys_event_flag_create_host(uint32_t, uint64_t);
        const int64_t flag1_rc = sys_event_flag_create_host(taskset_ea + CSTS_EVENT_FLAG_ID1, 0);
        if (flag1_rc != CELL_OK) return (s32)flag1_rc;
        const int64_t flag2_rc = sys_event_flag_create_host(taskset_ea + CSTS_EVENT_FLAG_ID2, 0);
        if (flag2_rc != CELL_OK) return (s32)flag2_rc;"""
        new = """    /* ASCENSION_M814_TASKSET2_EVENTFLAGS_CHECK_V1
     * Never silently publish a Taskset2 whose SPU-side task library cannot
     * create tasks because one of its two LV2 event flags was not allocated.
     * The previous code checked syscall status but never validated the IDs written to guest memory. */
        extern int64_t sys_event_flag_create_host(uint32_t, uint64_t);
        extern int64_t sys_event_flag_destroy_host(uint32_t);
        const uint32_t evf1_ea = taskset_ea + CSTS_EVENT_FLAG_ID1;
        const uint32_t evf2_ea = taskset_ea + CSTS_EVENT_FLAG_ID2;
        int64_t rc1 = sys_event_flag_create_host(evf1_ea, 0);
        uint32_t evf1 = vm_read32(evf1_ea);
        if (rc1 != CELL_OK || !evf1) {
            fprintf(stderr, "[cellSpurs] Taskset2 event flag #1 failed rc=0x%llX id=%u ea=0x%08X\\n",
                    (unsigned long long)rc1, evf1, evf1_ea);
            if (evf1) (void)sys_event_flag_destroy_host(evf1);
            return (s32)0x80410909u;
        }
        int64_t rc2 = sys_event_flag_create_host(evf2_ea, 0);
        uint32_t evf2 = vm_read32(evf2_ea);
        if (rc2 != CELL_OK || !evf2 || evf2 == evf1) {
            fprintf(stderr, "[cellSpurs] Taskset2 event flag #2 failed rc=0x%llX id=%u first=%u ea=0x%08X\\n",
                    (unsigned long long)rc2, evf2, evf1, evf2_ea);
            (void)sys_event_flag_destroy_host(evf1);
            if (evf2 && evf2 != evf1) (void)sys_event_flag_destroy_host(evf2);
            return (s32)0x80410909u;
        }
        fprintf(stderr, "[cellSpurs] Taskset2 event flags valid ids=%u/%u taskset=0x%08X\\n",
                evf1, evf2, taskset_ea);"""
        s = replace_once(s, old, new, "Taskset2 flag creation")
        spurs.write_text(s)

    event = root / "runtime/syscalls/sys_event.c"
    s = event.read_text()
    if "int64_t sys_event_flag_destroy_host(uint32_t flag_id)" not in s:
        anchor = "int64_t sys_event_flag_destroy(ppu_context* ctx)\n{"
        wrapper = """/* Host HLE counterpart used to roll back partial Taskset2 creation. */
int64_t sys_event_flag_destroy_host(uint32_t flag_id)
{
    ppu_context* c = (ppu_context*)calloc(1, sizeof(ppu_context));
    if (!c) return (int64_t)(int32_t)CELL_ENOMEM;
    c->gpr[3] = flag_id;
    int64_t rc = sys_event_flag_destroy(c);
    free(c);
    return rc;
}

"""
        s = replace_once(s, anchor, wrapper + anchor, "host event flag destroy wrapper")
        event.write_text(s)

    assert MARK in spurs.read_text()
    assert "sys_event_flag_destroy_host(uint32_t flag_id)" in event.read_text()
    print("[PASS] M8.14 Taskset2 event flags are checked, logged, and rolled back on partial failure")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, type=Path)
    args = ap.parse_args()
    apply(args.upstream)
