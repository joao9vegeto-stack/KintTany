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
require("library.requestExit()" in exit_button and "touchController.releaseAll()" not in exit_button,
        "SAIR must not synchronously re-enter the touch mutex on the UIKit thread")
disappear = body(APP, ".onDisappear {", "        .onAppear {")
require("library.requestExit()" in disappear and "touchController.releaseAll()" not in disappear,
        "surface teardown must leave controller reset to the joined native runtime")

inventory = body(ENGINE, "// Inventory is deliberately restricted", "const Image image = parseImage(path);")
require("loading_screen_final.bik" in inventory and "ATVI_logo.bik" in inventory,
        "startup inventory must include the Xenia-verified logo chain and final loading screen")
require("directory_iterator" not in inventory and 'extension != ".xxx"' not in inventory,
        "startup inventory must not enumerate every .bik/.xxx in the Movies folder")
require("playback_order=not_observed" in inventory,
        "inventory must never be presented as actual playback order")

read_trace = body(ENGINE, "const bool isVerifiedBootBink",
                  'if (readExtension == ".xxx" || readExtension == ".bik")')
require('readExtension == ".bik"' in read_trace and 'mediaParentLower == "movies"' in read_trace,
        "file-read sequence must be limited to startup Bink videos")
require("XOWUE_BINK_FILE_READ_ORDER" in read_trace and "playback_order_not_inferred=1" in read_trace,
        "Bink file reads must be distinguished from actual playback")
require('readExtension == ".xxx" || readExtension == ".bik"' not in read_trace,
        "the media read-order trace must not include cooked Unreal .xxx assets")

integrity_trace = body(ENGINE, 'if (readExtension == ".xxx" || readExtension == ".bik")',
                       "writeGuestIoStatus(base, ioStatus, readStatus, bytesRead);")
require("B92_XXX_INTEGRITY" in integrity_trace and "B92_BIK_INTEGRITY" in integrity_trace,
        "source-vs-guest integrity must cover both cooked .xxx assets and Bink .bik files")
require("sourceHash" in integrity_trace and "guestHash" in integrity_trace,
        "integrity verification must compare the on-disk read with guest memory")

thread_trace = body(ENGINE, "if (thread->startAddress == 0x82690DC0u", "entryFunction(childContext, memory->base);")
require("0x82690DC0u" in thread_trace and "0x83268358u" in thread_trace,
        "actual video and Bink decoder thread entries must be traced separately")
require("XOWUE_BINK_VIDEO_CONTEXT" in thread_trace,
        "video-thread context words must be retained to map playback to the opened Bink file")

guest_thread = body(ENGINE, "struct GuestThread {", "struct GuestAudioClient {")
require("vdRetrainCallCount" in guest_thread,
        "each guest video thread must maintain its own VdRetrainEDRAM call counter, not a decoded-frame count")
frame_marker = body(ENGINE, "void xowue_VdRetrainEDRAM(PPCContext &context) {",
                    "void xowue_VdRetrainEDRAMWorker(")
for token in ("XOWUE_VD_RETRAINEDRAM_CALL", "g_vdRetrainCallOrder", "vdRetrainCallCount",
              "thread->startAddress", "thread->startupAddress", "thread->startContext",
              "lastGuestPc", "lastGuestLr"):
    require(token in frame_marker,
            f"VdRetrainEDRAM call sample must retain {token}")
require("order <= 4u" in frame_marker and "order % 120u" in frame_marker,
        "VdRetrainEDRAM calls must be sampled, not mislabeled as decoded Bink frames")
require("context.r3.u32 = 0u;" in frame_marker,
        "frame observation must preserve VdRetrainEDRAM's existing success return")
require("g_vdRetrainCallOrder.store(0u" in ENGINE,
        "VdRetrainEDRAM call order must reset at the start of each XEX session")
persist = body(ENGINE, "bool shouldPersistRuntimeTrace(", "void persistRuntimeTrace(")
for token in ("XOWUE_VD_RETRAINEDRAM_CALL", "XOWUE_BINK_VIDEO_THREAD_START",
              "XOWUE_BINK_VIDEO_CONTEXT", "XOWUE_BINK_DECODER_THREAD_START",
              "XOWUE_BINK_FILE_READ_ORDER", "XOWUE_BINK_READ_PROGRESS"):
    require(token in persist, f"bounded runtime trace must persist {token}")
for token in ("XOWUE_VIDEO_THREAD_EXIT", "XOWUE_USER_EXIT", "XOWUE_INPUT_SUMMARY",
              "XOWUE_SESSION_TEARDOWN", "XOWUE_THREAD_JOINED",
              "XOWUE_THREAD_ORPHANED"):
    require(token in persist, f"bounded runtime trace must persist {token}")


swap_decode = body(ENGINE, "static bool decodeXenosSwapTexture(", "static bool decodeXenosBCTexture(")
require("fetchFormat==26u" in swap_decode and "component * 255u + 32767u" in swap_decode,
        "Xenos TextureFormat 26 must decode four 16-bit UNORM channels")
require("(fetchFormat==26u || fetchFormat==32u) ? 8u" in swap_decode,
        "TextureFormat 26 and RGBA16_FLOAT must use eight bytes per pixel with separate conversions")

touch_set = body(ENGINE, 'extern "C" void xowue_set_touch_controller_state(', 'extern "C" int xowue_set_runtime_trace_path')
require("g_xowueTouchAHostDownCount" in touch_set and "g_xowueTouchAHostUpCount" in touch_set,
        "host bridge must count A/CROSS press and release edges")
require("0x1000u" in touch_set and "fetch_add(1u, std::memory_order_relaxed)" in touch_set,
        "A/CROSS XInput mask must update atomic host-edge counters without synchronous file I/O")
require("recordRuntimeTrace(" not in touch_set and "persistGuestInputTrace(" not in touch_set,
        "UIKit touch setter must stay nonblocking and must not synchronously write diagnostic files")
input_state = body(ENGINE, "static uint32_t writeTouchGamepadState(", "static uint32_t writeTouchGamepadCapabilities(")
require("g_xowueTouchAGuestPollCount" in input_state and "state.buttons & 0x1000u" in input_state,
        "guest poll path must count polls that actually carry A/CROSS down")
require("host_a_down=%u host_a_up=%u guest_a_polls=%u" in ENGINE,
        "final input summary must distinguish host edges from guest-observed A state")
require("compactReverse" in ENGINE and "seenAotKeys" in ENGINE,
        "compact runtime diagnostic must remove repeated AOT hot-function/caller lines")

flow = body(ENGINE, "// These are media-adjacent PPC routines", "    // Check before diagnostic work")
require("0x822A0278u" not in flow,
        "the FName/NoneByteProperty helper must not be mislabeled as Bink playback")
require("XOWUE_MEDIA_PPC_FLOW sample=" in flow,
        "media-adjacent PPC samples must use an independent sample counter")
require("flowSample, guestAddress, hit" in flow,
        "the media-flow log must pass its own sample counter to snprintf")

require("test_xowue_1183_touch_exit_media.py" in WORKFLOW,
        "the workflow must run the Build 118.4 touch/exit/media regression test")
require("180" in APP and ".milliseconds(180)" in APP,
        "touch buttons and triggers must remain visible to the guest polling thread for 180 ms")
print("XOWUE_BUILD1184_TOUCH_EXIT_MEDIA_OK")
