#!/usr/bin/env python3
"""Build 108 regression contract: native audio bring-up and complete touch observability."""
from pathlib import Path

engine = Path("Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
audio = Path("iOS/App/XOWUEAudioBackend.mm").read_text(encoding="utf-8")
app = Path("iOS/App/XOWUEApp.swift").read_text(encoding="utf-8")
diagnostics = Path("iOS/App/XOWUEDiagnostics.swift").read_text(encoding="utf-8")
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
require("XOWUE_INPUT_NATIVE" in setter,
        "C++ touch-state reception must be logged")
require("inputNativeLogs" in setter,
        "native touch logging must be bounded")

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
require("XOWUE_INPUT_HOST" in send,
        "host-side touch events must be logged before guest consumption")

require('"XOWUE_INPUT_"' in diagnostics,
        "touch logs must trigger diagnostic summary refresh")
require('let input = Array(lines.filter { $0.contains("XOWUE_INPUT_") }.suffix(48))' in diagnostics,
        "compact summary must retain recent touch events")
require("+ boot + audioDriver + input + eventWaits" in diagnostics,
        "touch section must be included in the compact summary")

require("xowue_XInputGetState" in stubs and "XInputGetState" in stubs,
        "XInputGetState must remain in the generated import dispatcher")
require("xowue_XamInputGetState" in stubs and "XamInputGetState" in stubs,
        "XamInputGetState must remain in the generated import dispatcher")
require("test_xowue_build108_audio_input.py" in workflow,
        "CI must execute the Build 108 audio/input contract")

print("PASS: Build 108 audio bring-up, serial AVAudioEngine lifecycle, XInput dispatcher, and touch trace contract")
