#!/usr/bin/env python3
"""Build 108 regression contract: native audio bring-up and complete touch observability."""
from pathlib import Path

engine = Path("Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
audio = Path("iOS/App/XOWUEAudioBackend.mm").read_text(encoding="utf-8")
app = Path("iOS/App/XOWUEApp.swift").read_text(encoding="utf-8")
diagnostics = Path("iOS/App/XOWUEDiagnostics.swift").read_text(encoding="utf-8")
backend = Path("iOS/App/XOWUEVulkanBackend.m").read_text(encoding="utf-8")
stubs = Path("Runtime/generate_runtime_stubs.py").read_text(encoding="utf-8")
workflow = Path(".github/workflows/xowue-ios.yml").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


register_start = engine.index('if (api == "XAudioRegisterRenderDriverClient")')
register_end = engine.index('if (api == "XAudioUnregisterRenderDriverClient")', register_start)
register = engine[register_start:register_end]
require("XOWUEAudioStart()" in register,
        "render-driver registration must start the native audio backend")
require("XOWUE_AUDIO_BACKEND_START source=render_driver_register" in register,
        "render-driver fallback start must be recorded")
require("startXowueAudioWorker(base, callback)" in register,
        "guest callback worker must remain connected to the registered render client")

submit_start = engine.index('if (api == "XAudioSubmitRenderDriverFrame")')
submit_end = engine.index('if (api == "XamVoiceClose"', submit_start)
submit = engine[submit_start:submit_end]
require("XOWUE_AUDIO_BACKEND_STATE" in submit,
        "asynchronous native backend state changes must reach runtime diagnostics")
require("lastLoggedAudioBackendState" in submit,
        "backend state transition logging must be bounded")
require("peak=%.4f rms=%.4f" in submit,
        "guest PCM level telemetry must remain available")

require("audioControlQueue()" in audio, "native AVAudioEngine needs its own control queue")
require("DISPATCH_QUEUE_SERIAL" in audio, "audio engine lifecycle must be serialized")
require("startAudioOnControlQueue" in audio, "audio startup must execute on the audio queue")
require("dispatch_async(audioControlQueue()" in audio,
        "audio start/stop must not be dispatched through SwiftUI's main queue")
require("dispatch_get_main_queue" not in audio,
        "audio lifecycle must not depend on the UI main queue")
require("XOWUE_AUDIO_BACKEND_STARTED" in audio,
        "successful AVAudioEngine start must remain explicitly logged")

setter_start = engine.index('extern "C" void xowue_set_touch_controller_state(')
setter_end = engine.index('extern "C" int xowue_set_runtime_trace_path', setter_start)
setter = engine[setter_start:setter_end]
require("XOWUE_INPUT_NATIVE" not in setter,
        "C++ touch setter must not log synchronously on the caller thread")
require("recordRuntimeTrace" not in setter,
        "C++ touch setter must not perform synchronous runtime file I/O")
require("if (changed) ++g_touchController.packetNumber;" in setter,
        "touch packet sequence must still advance on state changes")

poll_start = engine.index("static uint32_t writeTouchGamepadState(")
poll_end = engine.index("static uint32_t writeTouchGamepadCapabilities(", poll_start)
poll = engine[poll_start:poll_end]
require("XOWUE_INPUT_POLL" in poll,
        "guest XInput poll calls must be recorded even without a changed packet")
require("XOWUE_INPUT_POLLED" in poll,
        "changed touch packets must still be recorded as guest-consumed input")

send_start = app.index("private func send() {", app.index("private final class XOWUETouchController"))
send_end = app.index("\n    }", send_start) + 6
send = app[send_start:send_end]
require("xowue_set_touch_controller_state(" in send,
        "Swift touch state must continue to enter the native controller")
require("XOWUE_INPUT_HOST" in send and "XOWUEDiagnostics.logInput(" in send,
        "host touch events must use asynchronous input logging")

require("static func logInput(_ message: String)" in diagnostics,
        "touch input must have a dedicated asynchronous logging API")
require("inputLogQueue.async" in diagnostics,
        "touch writes must run on a utility queue")
require("inputFilename" in diagnostics,
        "touch events must be preserved in a sidecar file")
important_start = diagnostics.index("let important = [")
important_end = diagnostics.index("if important.contains", important_start)
important = diagnostics[important_start:important_end]
require('"XOWUE_INPUT_"' not in important,
        "touch logs must not trigger expensive summary rebuilds")
require("inputLogQueue.sync {}" in diagnostics,
        "explicit summary/export must drain pending input writes")
require("inputSidecar" in diagnostics and "legacyInput" in diagnostics,
        "compact summary must merge sidecar and legacy input records")

require("AOT_PLATEAU_ACTIVE" in engine and "SPINLOCK_ACTIVE" not in engine,
        "AOT plateau must not be reported as a proven guest spinlock")

fps_start = backend.index("XOWUE_REAL_FPS")
fps_context = backend[max(0, fps_start - 2600):fps_start + 2600]
require("g_xowue_guest_swap_count" in fps_context and "xenos_swaps=" in fps_context,
        "guest-side telemetry must count Xenos swaps")
require("framebuffer_updates=" in fps_context and "metal_presents=" in fps_context,
        "Xenos swaps, CPU framebuffer updates and host presents must be separate")
require("XENOS SWAP" in backend and "FB %.1f/s" in backend and "METAL" in backend,
        "HUD must label all three distinct rates")
require("dispatch_async(KKDiagnosticQueue()" in backend,
        "thread dumps must not execute synchronously on the display-link thread")
render_start = backend.index("KKRenderFrame(KKVulkanState")
render_end = backend.index("\n@interface XOWUEVulkanView", render_start)
render = backend[render_start:render_end]
require("sampled_nonblack" in render and "sampled_bbox" in render,
        "GPU readback must retain bounded sample evidence")
require("for (size_t k=0;k<total;++k)" not in render,
        "GPU readback must not scan every framebuffer pixel")
require("QueueWaitIdle" in render,
        "existing Vulkan synchronization must remain intact")
require("sampled_nonblack" in workflow and "full_nonblack" not in workflow,
        "CI must validate bounded sample diagnostics")

require("xowue_XInputGetState" in stubs and "XInputGetState" in stubs,
        "XInputGetState must remain in the generated import dispatcher")
require("xowue_XamInputGetState" in stubs and "XamInputGetState" in stubs,
        "XamInputGetState must remain in the generated import dispatcher")
require("test_xowue_build108_audio_input.py" in workflow,
        "CI must execute the Build 108 audio/input contract")

print("PASS: XOWUE audio, asynchronous touch, separate frame rates, bounded GPU readback and AOT diagnostics")
