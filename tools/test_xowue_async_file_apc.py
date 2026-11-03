#!/usr/bin/env python3
"""Source-contract checks for completed XOWUE reads and APC notification ordering."""

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
        "file transfer must finish before the guest APC normal routine runs")

read = function_body(ENGINE, "void xowue_NtReadFile(", "\nvoid xowue_NtWriteFile(")
for token in (
    "const uint32_t apcRoutine = context.r5.u32 & ~1u;",
    "if (apcRoutine != 0u && apcThread)",
    "std::vector<uint8_t> bounce;",
    "bounce.resize(length);",
    "std::memcpy(base + buffer, bounce.data(), bytesRead);",
    "GuestFileCompletionSignalOnReturn completionSignal(file);",
    "GuestEventSignalOnReturn eventSignal(eventHandle);",
    "result = performRead(true);",
    "completionSignal.signalNow();",
    "eventSignal.signalNow();",
    "queueGuestApc(apcThread, apcRoutine, apcContext, ioStatus, 0u);",
    "context.r3.u32 = result.status;",
    "B103_ASYNC_NTREADFILE_SUBMIT",
    "B103_ASYNC_NTREADFILE_COMPLETE",
):
    require(token in read, f"NtReadFile missing required async/bounce-buffer behavior: {token}")

require(read.index("performRead(true)") < read.index("completionSignal.signalNow()"),
        "file read must finish before signaling file completion");
require(read.index("completionSignal.signalNow()") < read.index("eventSignal.signalNow()"),
        "file completion and final IOSB must precede event signaling");
require(read.index("eventSignal.signalNow()") < read.index("queueGuestApc(apcThread"),
        "the event must be signaled before the APC notification is queued");
require("std::move(completion)" not in read,
        "APC delivery must not own or defer the file transfer");
require("if (apcContext != 0u)" not in read,
        "a null APC context must suppress only the callback");
require("reinterpret_cast<char *>(base + buffer)" not in read,
        "NtReadFile must not read host files directly into guest memory")
require("B103_ASYNC_NTREADFILE_" in ENGINE,
        "async read markers must be emitted by the runtime")
require('event.find("B103_ASYNC_NTREADFILE_")' in ENGINE,
        "async read markers must survive runtime trace filtering")
require("B103_ASYNC_NTREADFILE_" in DIAGNOSTICS and "asyncFileIo" in DIAGNOSTICS,
        "diagnostic export must include async read submission/completion evidence")
require("test_xowue_async_file_apc.py" in WORKFLOW,
        "the XOWUE iOS workflow must execute this source-contract test")

print("PASS: XOWUE NtReadFile completes IOSB/event before queuing APC notification, including null APC context.")
