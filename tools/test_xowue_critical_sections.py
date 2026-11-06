#!/usr/bin/env python3
"""Regression checks for Xbox 360 RTL critical-section semantics."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")

def require(condition, message):
    if not condition:
        raise AssertionError(message)

require("std::atomic_ref<uint32_t> word(raw);" in ENGINE,
        "guest lock words must be updated atomically")
require("__builtin_bswap32(oldRaw)" in ENGINE and
        "__builtin_bswap32(static_cast<uint32_t>(newValue))" in ENGINE,
        "atomic guest lock words must preserve Xbox big-endian encoding")
require("atomicCompareExchangeGuestBe32(base, address + 0x10u, 0xFFFFFFFFu, 0u)" in ENGINE,
        "critical-section acquisition must use the guest lock_count CAS")
require("currentGuestThreadObjectAddress()" in ENGINE and
        "PPC_STORE_U32(address + 0x18u, currentThread)" in ENGINE,
        "owning_thread must contain the guest KTHREAD address, not the host thread id")
require("waitGuestObject(waitable, GuestTimeout{}, false)" in ENGINE,
        "contended critical sections must sleep on their embedded dispatcher event")
require("signalGuestWaitable(waitable);" in ENGINE,
        "the final owner release must wake a guest waiter")
require("PPC_STORE_U32(address + 0x08u, address + 0x08u)" in ENGINE and
        "PPC_STORE_U32(address + 0x0Cu, address + 0x08u)" in ENGINE,
        "critical-section dispatcher wait-list links must be initialized")
require("std::recursive_mutex" not in ENGINE and
        "criticalSectionLock(" not in ENGINE and
        "g_criticalSectionLocks" not in ENGINE,
        "host recursive mutexes must not replace the guest RTL critical section")
print("XOWUE_XBOX_CRITICAL_SECTIONS_OK")
