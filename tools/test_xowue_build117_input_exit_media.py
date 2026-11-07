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
require("navigation.exit tapped: terminating native PPC" in screen,
        "the SAIR tap diagnostic must remain")
require("VStack(spacing: 0)" not in screen,
        "the transparent full-screen VStack must not return")
require(".allowsHitTesting(false)" in screen,
        "passive overlay text must not intercept touch input")
require("library.requestExit()" in screen and "xowue_request_stop()" in APP,
        "the UI must reach the native scheduler stop entry point")

require("lastReadEof.store(readEof" in ENGINE,
        "NtReadFile must retain the real EOF result")
require("perMediaReadCounts" in ENGINE and "path_read=%u eof=%u" in ENGINE,
        "each BIK/XXX path must retain early reads and EOF beyond the old global 256-read cap")
require("B99_MEDIA_EOF_COMPLETION" in ENGINE,
        "both BIK and XXX EOFs must be correlated with guest completion signals")
require("B99_BIK_EOF_COMPLETION" in ENGINE,
        "the Bink EOF record must be emitted after the guest completion signal")
require("B94_STREAM_R10_WORD" in ENGINE,
        "the thread-11 stream object's r10 data must be captured")

print("XOWUE_BUILD117_INPUT_EXIT_MEDIA_GUARDS_OK")
