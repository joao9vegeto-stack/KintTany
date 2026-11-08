#!/usr/bin/env python3
"""Prevent the Build 114 guest-dispatcher critical-section regression."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
STUBS = (ROOT / "Runtime/generate_runtime_stubs.py").read_text(encoding="utf-8")


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
require("currentGuestKThread(context, base)" in enter and "owner == currentKThread" in enter and
        "g_currentGuestThreadId" not in enter,
        "RtlEnter must use KPCR.CurrentThread/KTHREAD identity for recursion")
require("sectionLock->try_lock()" in try_enter and "context.r3.u32 = 0u;" in try_enter,
        "RtlTryEnter must return false immediately on contention")
require("currentGuestKThread(context, base)" in try_enter and "owner == currentKThread" in try_enter and
        "g_currentGuestThreadId" not in try_enter,
        "RtlTryEnter must use the owning KTHREAD pointer for recursive acquisition")
require("sectionLock->unlock();" in leave and "owner != currentKThread" in leave and
        "currentGuestKThread(context, base)" in leave,
        "RtlLeave must validate KPCR.CurrentThread/KTHREAD ownership and release the matching host lock")
require("PPC_STORE_U32(address + 0x08, address + 0x08)" in initialise and
        "PPC_STORE_U32(address + 0x0C, address + 0x08)" in initialise and
        "PPC_STORE_U32(address + 0x08, address + 0x08)" in initialise_spin and
        "PPC_STORE_U32(address + 0x0C, address + 0x08)" in initialise_spin,
        "RTL critical-section dispatcher wait-list links must be self-initialized")
require("constexpr uint32_t kCurrentThreadOffset = 0x100u;" in ENGINE and
        "context.r13.u32 + kCurrentThreadOffset" in ENGINE and
        "loadGuestBe32(base, context.r13.u32 + kCurrentThreadOffset)" in ENGINE,
        "current KTHREAD must be read from KPCR.CurrentThread at r13 + 0x100")

require("g_criticalSectionLocks.clear();" in ENGINE,
        "session teardown must clear per-session RTL lock objects")

# Match MW2 Recompiled/Xenia's Xbox 360 spinlock ABI: the guest word stores
# the owning KPCR pointer (r13), acquired atomically in guest memory.
require("static bool tryAcquireGuestSpinLock(" in ENGINE and
        "__atomic_compare_exchange_n" in ENGINE and
        "__builtin_bswap32(owner)" in ENGINE and
        "__ATOMIC_ACQUIRE" in ENGINE and "__ATOMIC_RELEASE" in ENGINE,
        "spinlocks must use atomic big-endian guest-memory compare/exchange and release")
acquire = function_body("xowue_KeAcquireSpinLockAtRaisedIrql")
release = function_body("xowue_KeReleaseSpinLockFromRaisedIrql")
require("acquireGuestSpinLock(base, context.r3.u32, context.r13.u32)" in acquire,
        "KeAcquireSpinLockAtRaisedIrql must store the owning KPCR from r13")
require("releaseGuestSpinLock(base, context.r3.u32)" in release,
        "KeReleaseSpinLockFromRaisedIrql must release the guest-memory word")
require("g_guestSpinLocks" not in ENGINE and "g_spinLockMapMutex" not in ENGINE and
        "PPC_STORE_U32(address, 1u)" not in ENGINE,
        "host mutex maps and boolean lock values must not replace the guest spinlock ABI")

kf_start = ENGINE.index('if (api == "KfAcquireSpinLock")')
kf_end = ENGINE.index('if (api == "KfLowerIrql")', kf_start)
kf = ENGINE[kf_start:kf_end]
require("acquireGuestSpinLock(base, address, context.r13.u32)" in kf and
        "releaseGuestSpinLock(base, context.r3.u32)" in kf,
        "Kf acquire/release must share the same owner-aware guest lock primitive")
require("context.r4.u32" not in kf,
        "KfReleaseSpinLock must not read a nonexistent saved-IRQL argument")
require('if (api == "KeTryToAcquireSpinLockAtRaisedIrql")' in kf and
        "? 1u : 0u" in kf,
        "KeTryToAcquireSpinLockAtRaisedIrql must return the atomic acquisition result")
require('EXTRA_RUNTIME_DISPATCH_IMPORTS = {"KeTryToAcquireSpinLockAtRaisedIrql"}' in STUBS and
        '"KeTryToAcquireSpinLockAtRaisedIrql"' not in STUBS.split("COMPATIBILITY_IMPORTS = {", 1)[1].split("}", 1)[0],
        "KeTryToAcquireSpinLockAtRaisedIrql must remain a separately validated runtime ABI route, not a stale XEX import")

print("XOWUE_BUILD113_CRITICAL_SECTION_AND_SPINLOCK_ABI_OK")
