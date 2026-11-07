#!/usr/bin/env python3
"""Build 118.4 regression checks: live touch ports, exit dispatch and boot-media trace."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
APP = (ROOT / "iOS/App/XOWUEApp.swift").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/xowue-ios.yml").read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def body(source, start, end):
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


state = body(ENGINE, "static uint32_t writeTouchGamepadState(", "static uint32_t writeTouchGamepadCapabilities(")
require("if (userIndex > 3u)" in state,
        "touch input must be readable from every valid Xbox port, including the title's port 3")
require("state = g_touchController" in state and "PPC_STORE_U16(address + 4u" in state,
        "touch input must reach the guest XINPUT_STATE, not only the HUD")
require("reason=invalid_user_port" in state,
        "only out-of-range user indices may be rejected")

caps = body(ENGINE, "static uint32_t writeTouchGamepadCapabilities(", "static void traceXowueInputImport(")
require("if (userIndex > 3u)" in caps,
        "the same virtual controller must report capabilities on port 3")

xam_set = body(ENGINE, "void xowue_XamInputSetState(", "void xowue_VdQueryVideoFlags(")
require("userIndex <= 3u" in xam_set,
        "XAM rumble requests must recognize the mirrored virtual ports")

exit_button = body(APP, 'Button {\n                XOWUEDiagnostics.log("navigation.exit tapped', "            } label: {")
require(exit_button.index("library.requestExit()") < exit_button.index("touchController.releaseAll()"),
        "SAIR must dispatch native cancellation before touching the bridge mutex")
disappear = body(APP, ".onDisappear {", "        .onAppear {")
require(disappear.index("library.requestExit()") < disappear.index("touchController.releaseAll()"),
        "surface teardown must request cancellation before releasing input")

inventory = body(ENGINE, "// Inventory is deliberately restricted", "const Image image = parseImage(path);")
require("loading_screen_final.bik" in inventory and "ATVI_logo.bik" in inventory,
        "startup inventory must include the Xenia-verified logo chain and final loading screen")
require("directory_iterator" not in inventory and 'extension != ".xxx"' not in inventory,
        "startup inventory must not enumerate every .bik/.xxx in the Movies folder")
require("playback_order=not_observed" in inventory,
        "inventory must never be presented as actual playback order")

read_trace = body(ENGINE, "const bool isVerifiedBootBink", "writeGuestIoStatus(base, ioStatus, readStatus, bytesRead);")
require('readExtension == ".bik"' in read_trace and 'mediaParentLower == "movies"' in read_trace,
        "file-read sequence must be limited to startup Bink videos")
require("XOWUE_BINK_FILE_READ_ORDER" in read_trace and "playback_order_not_inferred=1" in read_trace,
        "Bink file reads must be distinguished from actual playback")
require('readExtension == ".xxx" || readExtension == ".bik"' not in read_trace,
        "the media read-order trace must not include cooked Unreal .xxx assets")

thread_trace = body(ENGINE, "XOWUE_BINK_VIDEO_THREAD_START", "entryFunction(childContext, memory->base);")
require("0x82690DC0u" in thread_trace and "0x83268358u" in thread_trace,
        "actual video and Bink decoder thread entries must be traced separately")
require("XOWUE_BINK_VIDEO_CONTEXT" in thread_trace,
        "video-thread context words must be retained to map playback to the opened Bink file")

flow = body(ENGINE, "// These are media-adjacent PPC routines", "    // Check before diagnostic work")
require("0x822A0278u" not in flow,
        "the FName/NoneByteProperty helper must not be mislabeled as Bink playback")
require("XOWUE_MEDIA_PPC_FLOW sample=" in flow,
        "media-adjacent PPC samples must use an independent sample counter")

require("test_xowue_1183_touch_exit_media.py" in WORKFLOW,
        "the workflow must run the Build 118.4 touch/exit/media regression test")
print("XOWUE_BUILD1184_TOUCH_EXIT_MEDIA_OK")
