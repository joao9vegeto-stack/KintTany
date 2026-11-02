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
    "targeted wait handle 0x115": "B97_WAIT_TARGET_BEGIN",
    "targeted signal handle 0x115": "B97_SIGNAL_TARGET",
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
}
failed = []
for label, token in required.items():
    ok = token in source
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if not ok:
        failed.append(label)

wait_start = source.index("uint32_t waitGuestObject(")
wait_end = source.index("\n}\n", wait_start)
wait_body = source[wait_start:wait_end]
if "markGuestWaitableSignaledLocked" in wait_body:
    failed.append("wait path must not fabricate signals")
    print("FAIL: wait path must not fabricate signals")
else:
    print("PASS: wait path does not fabricate signals")

if failed:
    raise SystemExit("XOWUE Build 97 diagnostic contract failed: " + "; ".join(failed))
print("XOWUE_BUILD97_VIDEO_DIAGNOSTICS source contract OK")
