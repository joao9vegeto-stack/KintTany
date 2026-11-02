#!/usr/bin/env python3
"""Build 97 source-contract checks for Wolverine movie, wait and Xenos evidence."""
from pathlib import Path

source = Path("Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
expected_xenia_movie_order = [
    "copyright.bik", "ravenlogo.bik", "atvi_logo.bik",
    "marvel_intro.bik", "fox_logo.bik", "ue3_logo.bik",
]
print("Xenia playback oracle: " + " -> ".join(expected_xenia_movie_order))

required = {
    "B97 records bypass legacy sampling": 'event.find("B97_")',
    "targeted wait handle 0x115": "B98_WAIT_BEGIN",
    "targeted event creation metadata": "B98_EVENT_CREATE",
    "targeted signal attempt handle 0x115": "B98_EVENT_SIGNAL_ATTEMPT",
    "targeted signal handle 0x115": "B97_SIGNAL_TARGET",
    "native KeInitializeEvent": "void xowue_KeInitializeEvent",
    "strict dispatcher-object pointer validation": "objectType != 0u && objectType != 1u",
    "invalid dispatcher-object diagnostics": "XOWUE_SYNC_REJECT",
    "per-address PPC code snapshots": "g_b97MoviePpcDumped[index].exchange",
    "bounded B98 wait diagnostics": "g_b98WaitTargetLogs.fetch_add",
    "PPC media callsite register capture": "B97_MOVIE_PPC",
    "PPC media instruction words": "B97_MOVIE_PPC_WORD",
    "movie scatter read evidence": "B97_MOVIE_SCATTER",
    "movie close / transition evidence": "B97_MOVIE_CLOSE",
    "Xenos decode boundary": "B97_XENOS_SWAP_DECODE",
    "real wait readiness": "waitable->signaled || waitable->unconsumedSignals",
    "PPC AOT execution telemetry": "recordAotFunctionExecution(guestAddress)",
    "PPC dispatch guard": "xowue_dispatch_guard::resolve",
    "scheduler cancellation": "g_schedulerStopRequested.load()",
    "guest memory validation": "validGuestRange",
    "Xenos frame commit": "NotifyGuestFrameCommitted",
    "Xenos frame submission boundary": "NotifyGuestFrameSubmitted",
    "scatter IOSB completion": "writeGuestIoStatus(base, ioStatus, status, total)",
    "scatter APC delivery": "queueGuestApc(g_currentGuestThread, context.r5.u32, context.r6.u32, ioStatus, 0u)",
    "scatter read diagnostics retained": "B95_SCATTER_READ",
    "file object completion starts auto-reset unsignaled": "file->completion->manualReset = false;\n    file->completion->signaled = false;",
    "file completion RAII implementation": "struct GuestFileCompletionSignalOnReturn final",
    "file completion init telemetry": "B99_FILE_COMPLETION_INIT",
    "file completion signal telemetry": "B99_FILE_COMPLETION_SIGNAL",
    "last-alias close wakes file waiters": "B99_FILE_COMPLETION_CLOSE",
}
failed = []
for label, token in required.items():
    ok = token in source
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if not ok:
        failed.append(label)

pointer_wait_start = source.index("std::shared_ptr<GuestWaitable> ensurePointerWaitable(")
pointer_wait_end = source.index("\n}\n", pointer_wait_start)
pointer_wait_body = source[pointer_wait_start:pointer_wait_end]
if "objectType != 0u && objectType != 1u" not in pointer_wait_body:
    failed.append("pointer wait must reject non-dispatcher guest memory")
    print("FAIL: pointer wait must reject non-dispatcher guest memory")
else:
    print("PASS: pointer wait rejects arbitrary guest memory")

wait_start = source.index("uint32_t waitGuestObject(")
wait_end = source.index("\n}\n", wait_start)
wait_body = source[wait_start:wait_end]
if "markGuestWaitableSignaledLocked" in wait_body:
    failed.append("wait path must not fabricate signals")
    print("FAIL: wait path must not fabricate signals")
else:
    print("PASS: wait path does not fabricate signals")


for function_name in ("xowue_NtReadFile", "xowue_NtReadFileScatter", "xowue_NtWriteFile"):
    function_start = source.index("void " + function_name + "(")
    function_end = source.find("\nvoid ", function_start + 6)
    if function_end < 0:
        function_end = len(source)
    function_body = source[function_start:function_end]
    if "GuestFileCompletionSignalOnReturn completionSignal(file);" not in function_body:
        failed.append(function_name + " must signal file completion on return")
        print("FAIL: " + function_name + " file completion guard")
    else:
        print("PASS: " + function_name + " file completion guard")

close_start = source.index("void xowue_NtClose(PPCContext &context) {")
close_end = source.index("\nstatic bool getGuestObjectPath", close_start)
close_body = source[close_start:close_end]
if "lastFileAlias && closedFileCompletion" not in close_body or "signalGuestWaitable(closedFileCompletion)" not in close_body:
    failed.append("last file alias close must signal completion")
    print("FAIL: last file alias close must signal completion")
else:
    print("PASS: last file alias close signals completion")

if failed:
    raise SystemExit("XOWUE Build 97 diagnostic contract failed: " + "; ".join(failed))
print("XOWUE_BUILD97_VIDEO_DIAGNOSTICS source contract OK")
