#!/usr/bin/env python3
"""Regression contract for exact UIKit dismissal and nonblocking Vulkan teardown."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "iOS/App/XOWUEApp.swift").read_text(encoding="utf-8")
BACKEND = (ROOT / "iOS/App/XOWUEVulkanBackend.m").read_text(encoding="utf-8")
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")

def require(condition, message):
    if not condition:
        raise AssertionError(message)

require(len(re.findall(r"private struct XOWUELandscapePresenter: UIViewControllerRepresentable", APP)) == 1,
        "there must be exactly one UIKit landscape presenter implementation")
require(len(re.findall(r"private final class XOWUELandscapePresentationCoordinator", APP)) == 1,
        "the exact-host presentation coordinator must have exactly one definition")

require("private final class XOWUELandscapePresentationCoordinator" in APP,
        "the presenter must retain a reference to the exact game host")
require("weak var presentedHost: XOWUELandscapeHostingController?" in APP and
        "weak var presentingController: UIViewController?" in APP,
        "controller tracking must not create a retain cycle")
require("host.presentingViewController" in APP and
        "presenter.presentedViewController === host" in APP and
        "presenter.dismiss(animated: false)" in APP,
        "dismissal must target the actual controller that presented the tracked host")
require("func makeCoordinator() -> XOWUELandscapePresentationCoordinator" in APP,
        "UIViewControllerRepresentable must persist the presentation coordinator")
require("runtime.stop duplicate request ignored" in APP,
        "repeated exit taps must not issue overlapping scheduler stops")

detach_start = BACKEND.index("- (void)didMoveToWindow")
detach_end = BACKEND.index("- (void)startBackend", detach_start)
detach = BACKEND[detach_start:detach_end]
require("[_displayLink invalidate]" in detach and "_displayLink = nil" in detach,
        "detaching the game surface must invalidate the CADisplayLink retain cycle")
require("cancelPreviousPerformRequestsWithTarget:self" in detach,
        "a queued backend startup must not execute after exit/detach")
require("- (void)startDisplayLinkIfNeeded" in BACKEND and
        "[self startDisplayLinkIfNeeded]" in detach,
        "reattaching a live backend must recreate its display link")
require("dispatch_async(KKGPUCompletionQueue()" in BACKEND and
        "KKDestroyVulkan(&localState)" in BACKEND,
        "GPU resources must be destroyed asynchronously off the UI thread")
assert "DeviceWaitIdle" not in detach

print("XOWUE_EXACT_EXIT_AND_RENDERER_TEARDOWN_OK")

request_stop = ENGINE[ENGINE.index('extern "C" void xowue_request_stop(void) {'):
                      ENGINE.index("static void rebuildGuestPathIndex();",
                                   ENGINE.index('extern "C" void xowue_request_stop(void) {'))]
require(request_stop.index("requestGuestSchedulerStop()") <
        request_stop.index("g_touchControllerMutex"),
        "native cancellation must be latched before any touch-controller mutex access")
require("std::try_to_lock" in request_stop,
        "exit diagnostics must never block on the touch-controller mutex")

finish = ENGINE[ENGINE.index("void finishGuestThread("):
                ENGINE.index("void requestGuestSchedulerStop()", ENGINE.index("void finishGuestThread("))]
require("thread->stateMutex" in finish and "thread->exited.store(true" in finish,
        "thread exit predicate must be published while holding its wait mutex")

stop_start = ENGINE.index("void requestGuestSchedulerStop()")
stop_end = ENGINE.index("constexpr uint32_t kGraphicsInterruptVblank", stop_start)
stop = ENGINE[stop_start:stop_end]
require("g_mainGuestThread->stateChanged.notify_all()" in stop and
        "g_graphicsInterruptThread->stateChanged.notify_all()" in stop,
        "native stop must wake suspended main and graphics threads as well as ordinary guest threads")

teardown = ENGINE[ENGINE.index("void stopGuestThreads() {"):
                  ENGINE.index("struct GuestSchedulerSessionGuard", ENGINE.index("void stopGuestThreads() {"))]
for token in ("XOWUE_SESSION_TEARDOWN", "XOWUE_THREAD_JOINED",
              "XOWUE_THREAD_ORPHANED", "g_touchController = {}"):
    require(token in teardown, f"teardown must implement and report {token}")

print("XOWUE_NONBLOCKING_EXIT_AND_THREAD_JOIN_OK")

ctx_checkpoint_start = ENGINE.index("void xowue_thread_checkpoint(uint32_t guestAddress,PPCContext &ctx){")
ctx_checkpoint_head = ENGINE[ctx_checkpoint_start:ctx_checkpoint_start + 240]
require("g_schedulerStopRequested.load(std::memory_order_acquire)" in ctx_checkpoint_head and
        "throw GuestThreadStopRequested{}" in ctx_checkpoint_head,
        "AOT function and loop checkpoints must throw on scheduler cancellation before diagnostic work")
plain_checkpoint_start = ENGINE.index("void xowue_thread_checkpoint(uint32_t guestAddress) {")
plain_checkpoint_head = ENGINE[plain_checkpoint_start:plain_checkpoint_start + 240]
require("g_schedulerStopRequested.load(std::memory_order_acquire)" in plain_checkpoint_head and
        "throw GuestThreadStopRequested{}" in plain_checkpoint_head,
        "plain AOT entry checkpoints must observe scheduler cancellation")
pump_start = ENGINE.index("struct GuestXenosPumpSessionGuard final")
pump_end = ENGINE.index("struct GuestThreadBinding final", pump_start)
pump_body = ENGINE[pump_start:pump_end]
require("!g_schedulerStopRequested.load(std::memory_order_acquire)" in pump_body,
        "Xenos pump worker must leave its loop when the guest scheduler is stopped")
require("XOWUE_VIDEO_THREAD_EXIT" in ENGINE,
        "video worker completion must be logged separately from VdRetrainEDRAM calls")
