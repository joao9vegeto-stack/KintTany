#!/usr/bin/env python3
"""Prevent the Build 114 guest-dispatcher critical-section regression."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def function_body(name):
    match = re.search(r"\bvoid\s+" + re.escape(name) +
                      r"\s*\(PPCContext\s*&context,\s*uint8_t\s*\*base\)\s*\{",
                      ENGINE)
    require(match is not None, f"{name} definition must exist")
    start = match.end()
    depth = 1
    for index in range(start, len(ENGINE)):
        if ENGINE[index] == "{":
            depth += 1
        elif ENGINE[index] == "}":
            depth -= 1
            if depth == 0:
                return ENGINE[start:index]
    raise AssertionError(f"{name} body has unbalanced braces")


# Build 113.7 guest RTL semantics are retained with cancellation-aware host locking for
# critical section with a recursive mutex. It did not create an Event object
# from the same guest address or park a PPC worker in waitGuestObject().
require("std::mutex g_criticalSectionMapMutex;" in ENGINE,
        "critical-section map mutex must remain present")
require("std::unordered_map<uint32_t, std::shared_ptr<std::recursive_timed_mutex>> g_criticalSectionLocks;" in ENGINE,
        "recursive timed-mutex map must remain present")
require("std::shared_ptr<std::recursive_timed_mutex> criticalSectionLock(uint32_t address)" in ENGINE,
        "guest RTL critical-section host lock helper must remain present")

# Generic pointer waitables must never reinterpret a known RTL critical
# section as an Xbox dispatcher event.
pointer_start = ENGINE.index("std::shared_ptr<GuestWaitable> ensurePointerWaitable")
pointer_end = ENGINE.index("bool readGuestTimeout", pointer_start)
pointer_body = ENGINE[pointer_start:pointer_end]
require("g_criticalSectionLocks.find(address) != g_criticalSectionLocks.end()" in pointer_body,
        "pointer waitable resolver must identify RTL critical-section addresses")
require("if (isCriticalSection || (objectType != 0u && objectType != 1u))" in pointer_body,
        "RTL critical sections must be rejected as dispatcher events")
require("critical_section=%u" in pointer_body,
        "sync rejection log must expose critical-section classification")

initialise = function_body("xowue_RtlInitializeCriticalSection")
initialise_spin = function_body("xowue_RtlInitializeCriticalSectionAndSpinCount")
enter = function_body("xowue_RtlEnterCriticalSection")
try_enter = function_body("xowue_RtlTryEnterCriticalSection")
leave = function_body("xowue_RtlLeaveCriticalSection")

for name, body in [
    ("RtlInitializeCriticalSection", initialise),
    ("RtlInitializeCriticalSectionAndSpinCount", initialise_spin),
    ("RtlEnterCriticalSection", enter),
    ("RtlTryEnterCriticalSection", try_enter),
    ("RtlLeaveCriticalSection", leave),
]:
    require("criticalSectionLock(address)" in body,
            f"{name} must use the per-address recursive timed mutex")
    for forbidden in (
        "waitGuestObject(", "signalGuestWaitable(",
        "atomicCompareExchangeGuestBe32(", "initialiseGuestCriticalSection("
    ):
        require(forbidden not in body,
                f"{name} must not route RTL lock semantics through {forbidden}")

require("sectionLock->try_lock_for(std::chrono::milliseconds(10))" in enter,
        "RtlEnter must wait in cancellable 10ms intervals")
require("g_schedulerStopRequested.load(std::memory_order_acquire)" in enter,
        "RtlEnter must unwind after native scheduler cancellation")
require("owner == g_currentGuestThreadId" in enter,
        "RtlEnter must preserve same-thread recursion and host-lock serialization")
require("sectionLock->try_lock()" in try_enter and "context.r3.u32 = 0u;" in try_enter,
        "RtlTryEnter must return false immediately on contention")
require("sectionLock->unlock();" in leave and "owner != g_currentGuestThreadId" in leave,
        "RtlLeave must validate owner and release the matching host lock")
require("g_criticalSectionLocks.clear();" in ENGINE,
        "session teardown must clear per-session RTL lock objects")

print("XOWUE_BUILD113_CRITICAL_SECTION_COMPATIBILITY_OK")
