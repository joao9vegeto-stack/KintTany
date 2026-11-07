#!/usr/bin/env python3
"""Regression contract for guest-written Xbox dispatcher Event SignalState."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")

def require(condition, message):
    if not condition:
        raise AssertionError(message)

helper_start = ENGINE.index("static uint32_t readGuestEventSignalStateLocked(")
helper_end = ENGINE.index("static void markGuestWaitableSignaledLocked(", helper_start)
helper = ENGINE[helper_start:helper_end]
require("waitable->kind != GuestWaitable::Kind::Event" in helper,
        "guest-memory adoption must not reinterpret semaphore/mutant/timer state")
require("loadGuestBe32(base, waitable->objectAddress + 4u)" in helper,
        "SignalState must be read from the guest dispatcher header in Xbox big-endian order")
require("waitable->signaled = true" in helper and
        "waitable->unconsumedSignals = 1u" in helper,
        "guest set state must make the host event waitable")
require("waitable->signaled = false" in helper and
        "waitable->unconsumedSignals = 0u" in helper,
        "guest reset state must clear the host event state")
require("B105_GUEST_EVENT_STATE_ADOPT" in helper,
        "state adoption must be visible in diagnostics")

single_start = ENGINE.index("uint32_t waitGuestObject(")
single_end = ENGINE.index("\nuint32_t waitGuestObjects(", single_start)
single = ENGINE[single_start:single_end]
require(single.count("adoptGuestEventMemorySignalStateLocked(waitable)") >= 3,
        "single-object waits must poll before readiness, in the loop and in the wait predicate")
require("guest_signal_state=0x%08X" in single,
        "wait diagnostics must include the raw guest SignalState")
require("markGuestWaitableSignaledLocked" not in single,
        "a wait must never fabricate a signal")

multi_start = ENGINE.index("uint32_t waitGuestObjects(")
multi_end = ENGINE.index("\nvoid signalGuestWaitable(", multi_start)
multi = ENGINE[multi_start:multi_end]
require("adoptGuestEventMemorySignalStateLocked(waitables[index])" in multi,
        "WaitAny and WaitAll must adopt guest writes for every candidate")

persist_start = ENGINE.index("bool shouldPersistRuntimeTrace(")
persist_end = ENGINE.index("\nvoid persistRuntimeTrace(", persist_start)
persist = ENGINE[persist_start:persist_end]
require('"B105_GUEST_EVENT_STATE_ADOPT"' in persist,
        "event state transitions must survive the bounded trace filter")

print("XOWUE_GUEST_EVENT_SIGNALSTATE_ADOPTION_OK")
