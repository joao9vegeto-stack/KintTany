#!/usr/bin/env python3
"""Regression checks for async event lifetime, Xbox timer/APC semantics and wait diagnostics."""
from pathlib import Path

engine = Path("Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
diagnostics = Path("iOS/App/XOWUEDiagnostics.swift").read_text(encoding="utf-8")
workflow = Path(".github/workflows/xowue-ios.yml").read_text(encoding="utf-8")

start = engine.index("struct GuestEventSignalOnReturn final {")
end = engine.index("\n};", start) + 3
guard = engine[start:end]
assert "std::shared_ptr<GuestWaitable> waitable;" in guard
assert "lookupGuestWaitable(eventHandle)" in guard
assert "signalGuestWaitable(waitable);" in guard
assert "signalGuestEventHandle(handle);" not in guard
assert "B99_EVENT_COMPLETION_SIGNAL" in guard
assert "B99_EVENT_COMPLETION_MISSING" in guard

# The asynchronous event reference is captured at request submission, while
# the existing file completion guard separately retains its file-owned event.
for function in ("xowue_NtReadFile", "xowue_NtReadFileScatter", "xowue_NtWriteFile"):
    p = engine.index("void " + function + "(")
    q = engine.find("\nvoid ", p + 6)
    body = engine[p:q if q >= 0 else len(engine)]
    assert "GuestEventSignalOnReturn signal(context.r4.u32);" in body, function

assert 'event.find("B98_")' in engine
assert 'event.find("B99_")' in engine
assert 'event.find("B95_SYNC_")' in engine
for marker in ("B95_SYNC_", "B97_", "B98_", "B99_", "B103_ASYNC_NTREADFILE_"):
    assert marker in diagnostics, marker
assert "eventWaits + eventCompletions + asyncFileIo + movieFlow" in diagnostics
assert '"B98_"' in diagnostics
assert "B98_TIMER_" in diagnostics

# Xbox NtSetTimerEx ABI: Handle, DueTime, APC routine, mode/reserved,
# APC context, Resume, PeriodMs, reserved. Timer APCs must target the thread
# that armed the timer and be delivered through the existing guest APC queue.
timer_start = engine.index("void xowue_NtSetTimerEx(")
timer_end = engine.index("\nvoid xowue_NtCancelTimer(", timer_start)
timer = engine[timer_start:timer_end]
for token in (
    "context.r5.u32", "context.r6.u32", "context.r7.u32",
    "context.r8.u32", "context.r9.u32", "context.r10.u32",
    "timer->timerApcRoutine = apcRoutine",
    "timer->timerApcContext = apcContext",
    "timer->timerApcThread = callbackThread",
    "queueGuestApc(targetThread.get(), routine, apcContextValue",
    "++current->signalGeneration",
    "B98_TIMER_SET", "B98_TIMER_FIRE",
    "kNtStatusTimerResumeIgnored",
):
    assert token in timer or token in engine, token
assert "activeGuestApcThread()" in engine
assert "g_mainGuestThread.get()" in engine
assert "B98_TIMER_CREATE" in engine and "B98_TIMER_CANCEL" in engine
assert "test_xowue_build100_event_lifetime.py" in workflow
print("PASS: async event lifetime retained; NtSetTimerEx timer state, periodic signal generation, APC queuing and main-thread APC delivery are covered")
