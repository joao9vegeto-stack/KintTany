#!/usr/bin/env python3
"""Source-contract regression for Xbox 360 timer/APC dispatch in XOWUE."""
from pathlib import Path

engine = Path("Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
stubs = Path("Runtime/generate_runtime_stubs.py").read_text(encoding="utf-8")
diagnostics = Path("iOS/App/XOWUEDiagnostics.swift").read_text(encoding="utf-8")
workflow = Path(".github/workflows/xowue-ios.yml").read_text(encoding="utf-8")

start = engine.index("void xowue_NtSetTimerEx(")
end = engine.index("\nvoid xowue_NtCancelTimer(", start)
timer = engine[start:end]
required = (
    "const uint32_t apcRoutine = context.r5.u32",
    "const uint32_t apcMode = context.r6.u32",
    "const uint32_t apcContext = context.r7.u32",
    "const uint32_t resume = context.r8.u32",
    "const uint32_t periodMs = context.r9.u32",
    "const uint32_t reserved = context.r10.u32",
    "timer->timerApcRoutine = apcRoutine",
    "timer->timerApcContext = apcContext",
    "timer->timerApcThread = callbackThread",
    "queueGuestApc(targetThread.get(), routine, apcContextValue",
    "++current->signalGeneration",
    "B98_TIMER_SET",
    "B98_TIMER_FIRE",
    "kNtStatusTimerResumeIgnored",
)
for token in required:
    assert token in timer, token
assert "GuestThread *activeGuestApcThread()" in engine
assert "g_mainGuestThread.get()" in engine
assert "B98_TIMER_CREATE" in engine and "B98_TIMER_CANCEL" in engine
assert "timer->timerArmed = true" in timer
assert "current->timerArmed = false" in timer
cancel_start = engine.index("void xowue_NtCancelTimer(")
cancel_end = engine.index("\nvoid xowue_ObCreateSymbolicLink(", cancel_start)
cancel = engine[cancel_start:cancel_end]
for token in ("wasArmed = timer->timerArmed", "PPC_STORE_U32(output, 0u)",
              "timer->timerArmed = false", "kNtStatusUnsuccessful"):
    assert token in cancel, token
assert "timer->signaled = false" not in cancel
assert "timer->unconsumedSignals = 0u" not in cancel
assert '"B98_"' in diagnostics
assert '$0.contains("B98_TIMER_")' in diagnostics
for export in ("NtCreateTimer", "NtSetTimerEx", "NtCancelTimer"):
    assert f'elif name == "{export}":' in stubs, export
assert "alertable=%u" in engine
assert "B98_TIMER_" in diagnostics
assert "test_xowue_build100_timer_apc.py" in workflow
print("PASS: Xbox timer ABI, export wiring, periodic signal state, APC queue target, main-thread APC delivery and persisted timer evidence")
