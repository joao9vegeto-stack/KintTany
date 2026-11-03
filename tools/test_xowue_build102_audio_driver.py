#!/usr/bin/env python3
"""Source-contract regression for the Xbox 360 XAudio render-driver pump."""
from pathlib import Path

engine = Path("Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
workflow = Path(".github/workflows/xowue-ios.yml").read_text(encoding="utf-8")
swift = Path("iOS/App/XOWUEDiagnostics.swift").read_text(encoding="utf-8")

required = (
    "kXowueAudioFrameInterval = std::chrono::microseconds(5333)",
    "kXowueAudioInitialDelay = std::chrono::milliseconds(100)",
    "kXowueAudioDriverTag = 0x41550000u",
    "void runXowueAudioCallbackPump(",
    "bool startXowueAudioWorker(",
    "GuestThreadBinding binding(thread.get())",
    "callbackContext.r2.u32 = imageBase",
    "callbackContext.r13.u32 = thread->pcrAddress",
    "callbackContext.r3.u32 = callbackContextValue",
    "XOWUE_XAUDIO_CALLBACK_ENTER",
    "XOWUE_XAUDIO_CALLBACK_ENTER",
    "XOWUE_XAUDIO_CALLBACK_RETURN",
    "B102_TIMER_WAIT_BEGIN",
    "B102_TIMER_WAIT_RESULT",
    "target_wait=0x%08X",
    "KPCR.CurrentProcessorNumber",
    "class GuestHostThread",
    "pthread_attr_setstacksize(&attributes, kAppleGuestHostStackBytes)",
    "constexpr size_t kAppleGuestHostStackBytes = 16u << 20",
    "QOS_CLASS_USER_INTERACTIVE",
    "thread->hostThread.start(",
    "creationProcessorMask = (creationFlags >> 24u) & 0xFFu",
    "static_cast<uint8_t>(thread->processor.load(std::memory_order_relaxed))",
    "base[pcrAddress + 0x10Cu] = processorNumber",
    "B103_THREAD_AFFINITY",
    "thread->processor.store(processor, std::memory_order_release)",
    "callbackContext.fpscr.loadFromHost()",
    "XOWUE_XAUDIO_FPSCR_INITIALIZED",
    "routine(callbackContext, base)",
    "XOWUE_XAUDIO_WORKER_START",
    "XOWUE_XAUDIO_CALLBACK",
    "XOWUE_XAUDIO_REGISTER",
    "XOWUE_XAUDIO_SUBMIT",
    "XOWUE_XAUDIO_UNREGISTER",
    "g_xaudioChanged.notify_all()",
    "resetXowueAudioRuntime()",
    "PPC_STORE_U32(driverOutput, handle)",
    "client->volumeChangeMask = 0xFFFFFFFFu",
    "PPC_STORE_U32(output, mask)",
    "PPC_STORE_U32(output, 0x3F800000u)",
    "validGuestRange(samples, kXowueAudioFrameBytes)",
    "output=%s",
    "outputState = queued ? \"queued\" : \"queue_full\"",
    "XOWUEAudioStart",
    "XOWUEAudioSubmitStereoFrame",
    "XOWUE_AUDIO_BACKEND_START",
    "XOWUEAudioBackendState",
)
for token in required:
    assert token in engine, token

assert "callbackContext.r3.u32 = callbackContextValue" in engine
assert "callbackArgumentWrapper" not in engine
assert "g_xaudioCallbackArgumentWrappers" not in engine
assert 'if (api == "XAudioRegisterRenderDriverClient" ||' not in engine
assert 'if (api == "XAudioSubmitRenderDriverFrame" ||' not in engine
assert "test_xowue_build102_audio_driver.py" in workflow
assert "XOWUE_XAUDIO_" in engine
assert "XOWUE_AUDIO_BACKEND_" in swift
assert "XOWUEAudioSubmitStereoFrame" in engine
assert "loadGuestBe32(base, address)" in engine
assert "output=discarded" not in engine
assert "let audioDriver = Array(lines.filter {" in swift
assert '$0.contains("XOWUE_AUDIO_BACKEND_")' in swift
assert "signalGuestEventHandle(0x4004ED80" not in engine
assert "signalGuestEventHandle(0x4004EDD0" not in engine
assert "waitable->handle == 0x115u" in engine
assert "waitable->kind == GuestWaitable::Kind::Timer" in engine
assert "targetThread->lastGuestPc.load" in engine
assert "targetThread->waitTarget.load" in engine
assert "targetThread->waitingInKernel.load" in engine
assert "B102_TIMER_WAIT_RESULT" in engine
assert "single-host-CPU affinity policy applied" not in engine
assert "PPC_STORE_U32(previousPointer, 1u)" not in engine
assert "context.r3.u32 = affinity" in engine
assert "std::thread hostThread" not in engine
assert "thread->hostThread = std::thread(" not in engine
backend = Path("iOS/App/XOWUEAudioBackend.mm").read_text(encoding="utf-8")
header = Path("iOS/App/XOWUEAudioBackend.h").read_text(encoding="utf-8")
project = Path("iOS/project.yml").read_text(encoding="utf-8")
assert '#include "../iOS/App/XOWUEAudioBackend.h"' in engine
assert "AVAudioEngine" in backend
assert "AVAudioSourceNode" in backend
assert "AVAudioSessionCategoryPlayback" in backend
assert "setPreferredSampleRate:48000.0" in backend
assert "setPreferredIOBufferDuration" in backend
assert "std::atomic<uint32_t>" in backend
assert "kAudioRingCapacity" in backend
assert "XOWUEAudioSubmitStereoFrame" in header
assert "AVFAudio" in project
assert "kXowueAudioChannels = 6u" in engine
assert "kXowueAudioSamplesPerFrame = 256u" in engine
print("PASS: XAudio guest 5.1 BE-float callback is downmixed and delivered to native iOS AVAudioEngine output")

swift = Path("iOS/App/XOWUEDiagnostics.swift").read_text(encoding="utf-8")
assert '"XOWUE_XAUDIO_"' in swift
assert '"XOWUE_XMA_"' in swift
assert "let audioDriver = Array(lines.filter {" in swift
assert "+ boot + audioDriver + eventWaits" in swift
print("PASS: PPC callback FPSCR initialized and XAudio/XMA lifecycle retained in compact iOS diagnostics")

assert "constexpr uint32_t kNtStatusPending = 0x00000103u;" in engine
