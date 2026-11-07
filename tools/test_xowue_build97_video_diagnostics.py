#!/usr/bin/env python3
"""Build 97 source-contract checks for Wolverine movie, wait and Xenos evidence."""
from pathlib import Path
import importlib.util

source = Path("Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
runtime_path = Path("Runtime/generate_runtime_stubs.py")
spec = importlib.util.spec_from_file_location("xowue_runtime_stubs_test", runtime_path)
assert spec is not None and spec.loader is not None
runtime_stubs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime_stubs)
assert 0x824ACBF8 in runtime_stubs.HOT_LOOP_CHECKPOINT_FUNCTIONS, (
    "SetState observed spinning after the movie handoff must be cancellable"
)
fixture = """PPC_FUNC_IMPL(__imp__sub_824ACBF8) {
loc_824AD5D8:
    ctx.r3.u32 = 0;
    goto loc_824AD5D8;
}
"""
instrumented, checkpoint_count = runtime_stubs.instrument_hot_loop_labels(fixture)
assert checkpoint_count == 1 and "xowue_thread_checkpoint(0x824AD5D8u, ctx);" in instrumented, (
    "SetState loop labels must observe cancellation and yield to the guest scheduler"
)
expected_xenia_movie_order = [
    "copyright.bik", "ravenlogo.bik", "atvi_logo.bik",
    "marvel_intro.bik", "fox_logo.bik", "ue3_logo.bik",
    "loading_screen_final.bik",
]
print("Xenia playback oracle: " + " -> ".join(expected_xenia_movie_order))

required = {
    "B97 records bypass legacy sampling": 'event.find("B97_")',
    "movie read order is explicit": "B105_MEDIA_READ_ORDER",
    "movie open order is explicit": "B105_MEDIA_OPEN_ORDER",
    "guest media call flow is chronological": "B105_MOVIE_PPC_FLOW",
    "directory enumeration is inventory-only": "XOWUE_MEDIA_ENUM_COMPLETE inventory_only=1",
    "guest SignalState polling": "adoptGuestEventMemorySignalStateLocked",
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
    "Xenos decode boundary": "decodeXenosSwapTexture(base, frontend.swapFetch.data(),",
    "Xenos decode failure accounting": "++summary.frameDecodeFailures;",
    "Xenos stale-frame rejection": "XENOS_STALE_GUEST_FRAME: swap_cpu_decode_failed",
    "Xenos decoded-frame commit": "NotifyGuestFrameCommitted()",
    "real wait readiness": "waitable->signaled || waitable->unconsumedSignals",
    "PPC AOT execution telemetry": "recordAotFunctionExecution(guestAddress)",
    "PPC dispatch guard": "xowue_dispatch_guard::resolve",
    "scheduler cancellation": "g_schedulerStopRequested.load()",
    "guest memory validation": "validGuestRange",
    "Xenos frame commit": "NotifyGuestFrameCommitted",
    "Xenos frame submission boundary": "NotifyGuestFrameSubmitted",
    "scatter IOSB completion": "writeGuestIoStatus(base, ioStatus, status, total)",
    "scatter APC delivery follows Xenia's non-null APC-context rule": "if (context.r6.u32 != 0u) queueGuestApc(",
    "scatter APC targets the current guest thread": "queueGuestApc(activeGuestApcThread(), context.r5.u32, context.r6.u32, ioStatus, 0u)",
    "Xbox FILE_SEGMENT_ELEMENT uses 32-bit pointer stride": "PPC_LOAD_U32(segments + segmentIndex * 4u)",
    "scatter segment-array bounds use 32-bit pointers": "static_cast<uint64_t>((length + 4095u) / 4096u) * 4u",
    "scatter diagnostics report segment stride and pointers": "segment_stride=4 first_segment=0x",
    "file objects retain NT synchronous-open flags": "file->synchronous = (options & (0x00000010u | 0x00000020u)) != 0u;",
    "scatter async handles return STATUS_PENDING": "context.r3.u32 = file->synchronous ? status : kNtStatusPending;",
    "NtReadFile async fallback returns STATUS_PENDING": "context.r3.u32 = file->synchronous ? result.status : kNtStatusPending;",
    "FILE_USE_FILE_POINTER_POSITION (-2) is supported": "requested != std::numeric_limits<uint64_t>::max() - 1u",
    "NtReadFile accepts current-position sentinel -2": "requestedOffset != std::numeric_limits<uint64_t>::max() - 1u",
    "scatter read diagnostics retained": "B95_SCATTER_READ",
    "runtime trace cap is bounded after targeted event sampling": "kMaxRuntimeTraceFileBytes = 4 * 1024 * 1024",
    "file object completion starts auto-reset unsignaled": "file->completion->manualReset = false;\n    file->completion->signaled = false;",
    "file completion RAII implementation": "struct GuestFileCompletionSignalOnReturn final",
    "file completion init telemetry": "B99_FILE_COMPLETION_INIT",
    "file completion signal telemetry": "B99_FILE_COMPLETION_SIGNAL",
    "last-alias close wakes file waiters": "B99_FILE_COMPLETION_CLOSE",
}
failed = []
inventory_start = source.index('recordRuntimeTrace("XOWUE_MEDIA_ENUM_COMPLETE')
inventory_end = source.index(");", inventory_start)
inventory_completion = source[inventory_start:inventory_end]
if "playback_order=not_observed" not in inventory_completion:
    failed.append("media inventory must explicitly avoid claiming playback order")
    print("FAIL: media inventory must explicitly avoid claiming playback order")
else:
    print("PASS: media inventory explicitly avoids claiming playback order")

for label, token in required.items():
    ok = token in source
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if not ok:
        failed.append(label)

scatter_apc_enqueue = "if (context.r6.u32 != 0u) queueGuestApc(activeGuestApcThread(), context.r5.u32, context.r6.u32, ioStatus, 0u);"
if source.count(scatter_apc_enqueue) != 3:
    failed.append("scatter and file-write completions must enqueue APC only with a non-null context")
    print("FAIL: scatter and file-write completions must enqueue APC only with a non-null context")
else:
    print("PASS: scatter and file-write completions enqueue APC only with a non-null context")

swap_start = source.index("decodeXenosSwapTexture(base, frontend.swapFetch.data(),")
swap_end = source.index("XENOS_STALE_GUEST_FRAME: swap_cpu_decode_failed", swap_start)
swap_body = source[swap_start:swap_end]
if "++frontend.decodedFrames;" not in swap_body or "NotifyGuestFrameCommitted()" not in swap_body:
    failed.append("successful Xenos decode must commit a decoded guest frame")
    print("FAIL: successful Xenos decode must commit a decoded guest frame")
else:
    print("PASS: successful Xenos decode commits a decoded guest frame")

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
