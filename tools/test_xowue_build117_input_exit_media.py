#!/usr/bin/env python3
"""Guard XOWUE's native UIKit input, isolated exit hit-testing and Bink handoff."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "iOS/App/XOWUEApp.swift").read_text(encoding="utf-8")
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


require("XOWUEButtonTouchSurface: UIViewRepresentable" in APP,
        "gamepad buttons must be backed by UIKit")
require("override func touchesBegan(" in APP and "override func touchesEnded(" in APP,
        "face buttons and triggers need explicit down/up callbacks")
require("override func touchesCancelled(" in APP,
        "iOS cancellation must always release the button state")
require("isMultipleTouchEnabled = true" in APP,
        "simultaneous touch input must be enabled")
require("XOWUEStickTouchSurface: UIViewRepresentable" in APP,
        "analogue input must use the UIKit touch surface")
require(APP.count(".position(x:") >= 8,
        "ABXY and D-pad views must use final explicit coordinates")
require(".gesture(DragGesture(minimumDistance: 0)" not in APP,
        "the old SwiftUI drag-based touch recognizers must be removed")

screen_start = APP.index("private struct XOWUEGameSurfaceScreen: View")
screen_end = APP.index("@MainActor\nprivate final class XOWUETouchController", screen_start)
screen = APP[screen_start:screen_end]
require('.overlay(alignment: .topLeading)' in screen,
        "SAIR must be an isolated top-leading overlay")
require(".frame(minWidth: 96, minHeight: 48)" in screen and
        ".contentShape(Rectangle())" in screen and ".zIndex(1000)" in screen,
        "SAIR must expose a large rectangular hit target above the game and HUD")
require("navigation.exit tapped: dispatching native cancellation" in screen,
        "the SAIR tap diagnostic must remain")
require("VStack(spacing: 0)" not in screen,
        "the transparent full-screen VStack must not return")
require(".allowsHitTesting(false)" in screen,
        "passive overlay text must not intercept touch input")
require("library.requestExit()" in screen and "xowue_request_stop()" in APP,
        "the UI must reach the native scheduler stop entry point")

require("result.eof = readEof" in ENGINE and "result.sequence = file->lastReadSequence.fetch_add" in ENGINE,
        "NtReadFile must retain EOF and sequence on the exact transfer result")
require("file->lastReadEof" not in ENGINE and "file->lastReadOffset" not in ENGINE,
        "EOF completion must not read a mutable per-file snapshot that another APC can overwrite")
require("readEof ? 1u : 0u" in ENGINE and "readReachedEof" not in ENGINE,
        "B105 media ordering must label the current read, not the previous read")
require("perMediaReadCounts" in ENGINE and
        "XOWUE_BINK_FILE_READ_ORDER order=%u path_read=%u file_read_only=1 playback_order_not_inferred=1 eof=%u" in ENGINE,
        "each verified boot BIK must retain per-file read sequence and EOF without implying playback order")
require("B99_MEDIA_EOF_COMPLETION" in ENGINE,
        "both BIK and XXX EOFs must be correlated with guest completion signals")
require("B99_BIK_EOF_COMPLETION" in ENGINE,
        "the Bink EOF record must be emitted after the guest completion signal")
require("completionSignal.signalNow(result.sequence, result.offset, result.bytesRead" in ENGINE,
        "sync and APC-backed reads must signal with the exact transfer metadata")
require("readCompleted && readEof" in ENGINE,
        "a failed or early-return read must not inherit an older transfer's EOF")
require("B94_STREAM_R10_WORD" in ENGINE,
        "the thread-11 stream object's r10 data must be captured")

for api, slot in [
    ("XInputGetState", 0), ("XamInputGetState", 1),
    ("XInputGetCapabilities", 2), ("XamInputGetCapabilities", 3),
    ("XamInputGetCapabilitiesEx", 4), ("XInputSetState", 5),
    ("XamInputSetState", 6),
]:
    require(f'traceXowueInputImport({slot}u, "{api}"' in ENGINE,
            f"{api} must expose its actual guest import call count and ABI arguments")
require("XOWUE_INPUT_API api=%s call=%u" in ENGINE,
        "input import tracing must be bounded and correlated to the PPC caller")
require("constexpr off_t kMaxGuestInputTraceFileBytes = 256 * 1024" in ENGINE,
        "expanded input diagnostics must retain the existing bounded sidecar size")

print("XOWUE_BUILD117_INPUT_EXIT_MEDIA_GUARDS_OK")
