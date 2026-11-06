#!/usr/bin/env python3
"""Build 110 regression contract: audio, XAM input semantics, independent taps and game FPS."""
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
require("kXInputFlagGamepad = 0x00000001u" in engine,
        "XAM GAMEPAD flag must retain the documented low-bit value")
require("kXInputFlagAnyUser = 1u << 30u" in engine,
        "XAM ANY_USER must use bit 30, not bit 0")
require("(userIndex & 0xFFu) == 0xFFu" in engine,
        "XUSER_INDEX_ANY must be recognized on the XAM input path")
require("xowueXamFlagsAllowGamepad(flags)" in engine,
        "XAM state/capability queries must reject non-gamepad device requests")
require("xowueNormalizeXamUserIndex(context.r3.u32, flags)" in engine,
        "XamInputGetState must normalize ANY_USER and XUSER_INDEX_ANY")
require("xowueNormalizeXamUserIndex(context.r4.u32, flags)" in engine,
        "XamInputGetCapabilitiesEx must use its real user/flags argument positions")
require("if (userIndex != 0u)" in engine,
        "only the single connected touch gamepad at index zero may report connected")

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
require("buttonReleaseGeneration" in app and ".milliseconds(120)" in app,
        "short button taps must remain available for at least one guest input poll")
require("triggerReleaseGeneration" in app,
        "short trigger taps must have independent release scheduling")
require("A/B/X/Y can no longer steal a neighbouring button's touch" in app,
        "ABXY touch targets must be non-overlapping")
require("size: 44).offset(y: -34)" in app and ".frame(width: 116, height: 116)" in app,
        "ABXY geometry must leave disjoint hit areas for all four face buttons")
require("buttonReleaseGeneration[mask, default: 0] &+= 1" in app,
        "repeated taps must cancel only the same button's pending release")

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

fps_start = backend.index("XOWUE_GAME_FPS")
fps_context = backend[max(0, fps_start - 2600):fps_start + 2600]
fps_start = backend.index("const uint32_t gameVdSwapCallsNow")
fps_end = backend.index("if (now - _lastStallDiagnostic", fps_start)
fps_context = backend[fps_start:fps_end]
require("g_xowue_game_vdswap_request_count" in fps_context and "gameVdSwapRequestRate" in fps_context,
        "game FPS must derive from the direct guest VdSwap API request counter")
require("guest_vdswap_calls=" in fps_context and "g_xowue_guest_swap_count" not in fps_context,
        "game FPS must count successful guest VdSwap calls, not PM4/XE_SWAP consumption")
vd_start = engine.index("void xowue_VdSwap(")
vd_end = engine.index("void xowue_VdInitializeScalerCommandBuffer", vd_start)
vd_swap = engine[vd_start:vd_end]
require("xowue_vulkan_backend_game_vdswap_request()" in vd_swap,
        "only a successful guest VdSwap call may increment game FPS")
require("guest_content_updates=" in fps_context and "metal_host_presents=" in fps_context,
        "content updates and host presents must remain separate diagnostics")
require('@" FPS JOGO %.1f"' in backend and "XENOS SWAP" not in backend,
        "HUD must show game FPS only, never a Xenos/Metal refresh counter")
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

print("PASS: XOWUE audio, XAM/XInput semantics, independent touch pulses, game VdSwap FPS, bounded GPU readback and AOT diagnostics")
