#!/usr/bin/env python3
"""Regression contract for exact UIKit dismissal and nonblocking Vulkan teardown."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "iOS/App/XOWUEApp.swift").read_text(encoding="utf-8")
BACKEND = (ROOT / "iOS/App/XOWUEVulkanBackend.m").read_text(encoding="utf-8")

def require(condition, message):
    if not condition:
        raise AssertionError(message)

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
