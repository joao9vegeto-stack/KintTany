#!/usr/bin/env python3
"""Regression contract for atomic NT dispatcher WaitAny/WaitAll semantics."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "Runtime/XOWUEEngine.cpp").read_text(
    encoding="utf-8"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


start = SOURCE.index("uint32_t waitGuestObjects(")
end = SOURCE.index("\nvoid signalGuestWaitable(", start)
WAIT = SOURCE[start:end]

require("GuestWaitStateScope waitState(waitTarget);" in WAIT,
        "multi-object waits must publish their wait target for stall diagnostics")
require("std::sort(lockOrder.begin(), lockOrder.end(), std::less<GuestWaitable *>{});" in WAIT,
        "all dispatcher objects must be locked in a stable global order")
require("lockOrder.erase(std::unique(lockOrder.begin(), lockOrder.end()), lockOrder.end());" in WAIT,
        "duplicate waitable references must not deadlock by locking the same mutex twice")
require("std::vector<std::unique_lock<std::mutex>> locks;" in WAIT and
        "locks.emplace_back(waitable->mutex);" in WAIT,
        "the complete wait set must be held concurrently")
require("const auto readyIndexLocked = [&]() -> int32_t" in WAIT,
        "readiness evaluation must have a lock-already-held form")
require("const auto readyIndex = [&]() -> int32_t" in WAIT and
        "return readyIndexLocked();" in WAIT,
        "condition-variable predicates must inspect a coherent locked wait set")
require("const auto consumeWaitableLocked =" in WAIT,
        "object consumption must be separated from lock acquisition")
require("consumeWaitableLocked(waitable);" in WAIT,
        "WaitAll must consume each object while holding the complete set")
require("auto objectLocks = lockAllWaitables();" in WAIT,
        "the whole wait set must be locked before deciding whether the wait succeeds")
require("g_waitSetChanged.wait_until(waitLock, wakeDeadline" in WAIT and
        "std::chrono::milliseconds(16)" in WAIT,
        "bounded wait slices must remain so a missed notification cannot strand a waiter")

loop = WAIT.index("for (;;)")
lock_pos = WAIT.index("auto objectLocks = lockAllWaitables();", loop)
scope_open = WAIT.rfind("            {\n", 0, lock_pos)
scope_close = WAIT.index("\n            }\n            if (selected < 0", lock_pos)
locked_decision = WAIT[scope_open:scope_close]
require("selected = readyIndexLocked();" in locked_decision,
        "readiness must be checked after acquiring the entire lock set")
require("for (const auto &waitable : waitables)" in locked_decision,
        "WaitAll must consume its whole set before releasing any object lock")
require("auto &waitable = waitables[static_cast<size_t>(selected)];" in locked_decision,
        "WaitAny must consume the selected object before releasing the same lock set")
require("return kNtStatusWait0;" in locked_decision and
        "return kNtStatusWait0 + static_cast<uint32_t>(selected);" in locked_decision,
        "successful wait statuses must only be returned from the atomic decision scope")
require("std::lock_guard<std::mutex> objectLock(waitable->mutex);" not in locked_decision,
        "the consume path must not release/reacquire a single object after readiness")

print("XOWUE_ATOMIC_MULTIWAIT_CONTRACT_OK")
