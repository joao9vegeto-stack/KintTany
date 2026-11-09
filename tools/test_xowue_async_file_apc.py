#!/usr/bin/env python3
"""Source-contract checks for MW2-style deferred, APC-backed XOWUE file reads."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
DIAGNOSTICS = (ROOT / "iOS/App/XOWUEDiagnostics.swift").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/xowue-ios.yml").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def function_body(source: str, start: str, end: str) -> str:
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


apc = function_body(ENGINE, "struct GuestApc {", "};")
require("std::function<void()> completion;" in apc,
        "GuestApc must own deferred I/O completion work")

queue = function_body(ENGINE, "void queueGuestApc(", "\n}")
require("std::function<void()> completion = {}" in queue,
        "queueGuestApc must accept deferred completion work")
require("std::move(completion)" in queue,
        "queueGuestApc must move completion work into the APC queue")

delivery = function_body(ENGINE, "bool deliverPendingGuestApcs(", "\n}")
require("apc.completion()" in delivery,
        "APC delivery must execute deferred I/O completion")
require(delivery.index("apc.completion()") < delivery.index("findGuestFunction(apc.routine)"),
        "deferred file transfer must finish before the guest APC routine runs")

read = function_body(ENGINE, "void xowue_NtReadFile(", "\nvoid xowue_NtWriteFile(")
for token in (
    "const uint32_t apcRoutine = context.r5.u32 & ~3u;",
    "if (apcRoutine != 0u && apcThread)",
    "writeGuestIoStatus(base, ioStatus, kNtStatusPending, 0u);",
    "auto completion = [performRead, file, base, ioStatus, eventHandle,",
    "result = performRead(true);",
    "GuestFileCompletionSignalOnReturn completionSignal(file);",
    "GuestEventSignalOnReturn eventSignal(eventHandle, eventWaitable);",
    "completionSignal.signalNow(result.sequence, result.offset, result.bytesRead,",
    "queueGuestApc(apcThread, apcRoutine, apcContext, ioStatus, 0u, std::move(completion));",
    "completionSignal.signalNow(result.sequence, result.offset, result.bytesRead,",
    "!hasSuppliedEvent);",
    "context.r3.u32 = kNtStatusPending;",
    "B103_ASYNC_NTREADFILE_SUBMIT",
    "B103_ASYNC_NTREADFILE_COMPLETE",
):
    require(token in read, f"NtReadFile missing deferred APC/bounce-buffer behavior: {token}")

async_start = read.index("if (apcRoutine != 0u && apcThread)")
async_end = read.index("if (apcRoutine != 0u && !apcThread)", async_start)
async_read = read[async_start:async_end]
completion_start = async_read.index("auto completion =")
completion_end = async_read.index("\n        };", completion_start)
completion_body = async_read[completion_start:completion_end]

require(async_read.index("writeGuestIoStatus(base, ioStatus, kNtStatusPending, 0u);") <
        async_read.index("queueGuestApc("),
        "IOSB must report STATUS_PENDING before the APC is queued")
require("result = performRead(true);" in completion_body,
        "file transfer must be owned by the deferred APC completion")
require(completion_body.index("result = performRead(true);") <
        completion_body.index("completionSignal.signalNow(result.sequence") <
        completion_body.index("eventSignal.signalNow();"),
        "final IOSB and guest buffer must be published before completion signals")
require("resetGuestWaitableForIo(eventWaitable)" in read and
        "resetGuestWaitableForIo(file->completion)" in read,
        "each NT read must reset only its selected completion wait object")
require("!hasSuppliedEvent" in completion_body and
        "GuestEventSignalOnReturn eventSignal(eventHandle, eventWaitable);" in completion_body,
        "a supplied request event must replace, not accompany, the file wait object")
require("context.r3.u32 = result.status;" in read,
        "an inline-completed read must return its final NT status, not false STATUS_PENDING")
require("eventWaitable->kind != GuestWaitable::Kind::Event" in read,
        "a non-null invalid event handle must be rejected instead of silently ignored")
require(completion_end < async_read.index("queueGuestApc("),
        "the APC must be queued with the completed deferred-work closure")
require("std::move(completion)" in async_read,
        "APC queue must own the deferred transfer closure")
require("context.r3.u32 = kNtStatusPending;" in async_read,
        "NtReadFile must return STATUS_PENDING for APC-backed reads")

require("std::vector<uint8_t> bounce;" in read and
        "std::memcpy(base + buffer, bounce.data(), bytesRead);" in read,
        "file data must pass through a host bounce buffer into guest memory")
require("B103_ASYNC_NTREADFILE_" in ENGINE,
        "async read markers must be emitted by the runtime")
require('event.find("B103_ASYNC_NTREADFILE_")' in ENGINE,
        "async read markers must survive runtime trace filtering")
require("B103_ASYNC_NTREADFILE_" in DIAGNOSTICS and "asyncFileIo" in DIAGNOSTICS,
        "diagnostic export must include async read submission/completion evidence")
require("test_xowue_async_file_apc.py" in WORKFLOW,
        "the XOWUE iOS workflow must execute this source-contract test")



# User APCs are delivered only by alertable waits, never by IRQL/critical-region transitions.
irql = function_body(ENGINE, 'if (api == "KfReleaseSpinLock")', 'if (api == "DbgBreakPoint")')
require("deliverPendingGuestApcs()" not in irql,
        "lowering IRQL or releasing a spinlock must not deliver user APCs")

leave_critical = function_body(ENGINE, "void xowue_KeLeaveCriticalRegion(", "\nvoid xowue_KeRaiseIrqlToDpcLevel(")
require("deliverPendingGuestApcs()" not in leave_critical,
        "leaving a critical region must not deliver user APCs")

delay = function_body(ENGINE, "void xowue_KeDelayExecutionThread(", "\nvoid ")
require("const bool alertable = (context.r4.u32 & 0xFFu) != 0u;" in delay and
        "if (alertable && deliverPendingGuestApcs())" in delay,
        "KeDelayExecutionThread may deliver user APCs only when alertable")
require("context.r3.u32 = kNtStatusUserApc;" in delay and
        delay.index("context.r3.u32 = kNtStatusUserApc;") <
        delay.index("const uint32_t intervalPointer"),
        "an APC delivered at an alertable delay must return STATUS_USER_APC")
require("std::this_thread::yield();" in delay,
        "zero/non-negative KeDelayExecutionThread intervals must yield instead of spin")
require("alertable && guestApcCanInterruptWait()" in delay,
        "an APC queued during an alertable relative delay must interrupt the wait")

print("PASS: XOWUE NtReadFile defers APC transfers, selects one reset completion object, and returns final status for inline reads.")
