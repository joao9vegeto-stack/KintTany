#!/usr/bin/env python3
"""Source contract test for M8.14 Taskset2 event-flag validation."""
from pathlib import Path
import argparse

def check(root):
    root = Path(root)
    spurs = (root / "libs/spurs/cellSpurs.c").read_text()
    event = (root / "runtime/syscalls/sys_event.c").read_text()
    required = [
        "ASCENSION_M814_TASKSET2_EVENTFLAGS_CHECK_V1",
        "int64_t rc1 = sys_event_flag_create_host(evf1_ea, 0);",
        "int64_t rc2 = sys_event_flag_create_host(evf2_ea, 0);",
        "if (rc1 != CELL_OK || !evf1)",
        "if (rc2 != CELL_OK || !evf2 || evf2 == evf1)",
        "sys_event_flag_destroy_host(evf1)",
        "Taskset2 event flags valid ids=%u/%u",
    ]
    for item in required:
        assert item in spurs, f"missing Taskset2 validation contract: {item}"
    assert "int64_t sys_event_flag_destroy_host(uint32_t flag_id)" in event
    # Guard against regression to unchecked calls.
    assert "sys_event_flag_create_host(taskset_ea + CSTS_EVENT_FLAG_ID1, 0);" not in spurs
    assert "sys_event_flag_create_host(taskset_ea + CSTS_EVENT_FLAG_ID2, 0);" not in spurs
    print("[PASS] M8.14 Taskset2 flags: return codes, IDs, duplicate IDs, rollback, and diagnostics")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, type=Path)
    check(ap.parse_args().upstream)
