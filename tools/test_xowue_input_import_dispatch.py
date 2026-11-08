#!/usr/bin/env python3
"""Verify XAM input imports are wired by the generated PPC runtime stubs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
GENERATOR = (ROOT / "Runtime/generate_runtime_stubs.py").read_text(encoding="utf-8")
APP = (ROOT / "iOS/App/XOWUEApp.swift").read_text(encoding="utf-8")

MAPPINGS = {
    "XInputGetState": "xowue_XInputGetState",
    "XamInputGetState": "xowue_XamInputGetState",
    "XamInputGetKeystroke": "xowue_XamInputGetKeystroke",
    "XamInputGetKeystrokeEx": "xowue_XamInputGetKeystrokeEx",
    "XInputGetCapabilities": "xowue_XInputGetCapabilities",
    "XamInputGetCapabilities": "xowue_XamInputGetCapabilities",
    "XamInputGetCapabilitiesEx": "xowue_XamInputGetCapabilitiesEx",
    "XInputSetState": "xowue_XInputSetState",
    "XamInputSetState": "xowue_XamInputSetState",
}

def require(condition, message):
    if not condition:
        raise AssertionError(message)

require("imports = sorted(set(IMPORT_RE.findall(shared)))" in GENERATOR,
        "the generator must derive stubs from the actual XEX import declarations")
require('code.append("\\txowue_thread_checkpoint();")' in GENERATOR,
        "every generated import stub must retain the PPC cancellation checkpoint")
for api, handler in MAPPINGS.items():
    require(f'elif name == "{api}":' in GENERATOR,
            f"{api} must have an explicit generated import branch")
    require(f'code.append("\\t{handler}(ctx, base);")' in GENERATOR,
            f"{api} must dispatch to {handler}")
    require(f"void {handler}(PPCContext &context, uint8_t *base)" in ENGINE,
            f"{handler} must be implemented by the native runtime")

require("GuestInputKeystroke" in ENGINE and "g_guestInputKeystrokeQueues" in ENGINE,
        "touch button edges must also be queued for XAM keystroke consumers")
require("queueTouchKeystrokeTransitions(previous, current)" in ENGINE and
        "XOWUE_INPUT_KEYSTROKE event=1" in ENGINE,
        "press and release edges must be delivered through XamInputGetKeystroke")
require('void xowue_XamInputGetKeystroke(PPCContext &, uint8_t *);' in GENERATOR and
        'void xowue_XamInputGetKeystrokeEx(PPCContext &, uint8_t *);' in GENERATOR and
        '"XamInputGetKeystroke", "XamInputGetKeystrokeEx"' in GENERATOR,
        "both XAM keystroke exports must be declared and classified as implemented")
require("kXInputErrorEmpty = 0x000010D2u" in ENGINE and
        "XamInputGetKeystrokeEx" in GENERATOR,
        "XAM keystroke APIs must return X_ERROR_EMPTY and both export variants must be generated")
require("XOWUE_INPUT_CALLSITE" in ENGINE and "loadGuestBe32(base, start + index * 4u)" in ENGINE,
        "input diagnostics must capture PPC instructions around the real XamInputGetState caller")
require("const uint32_t returnAddress = static_cast<uint32_t>(context.lr);" in ENGINE and
        "context.lr.u32" not in ENGINE,
        "PPCContext LR is a scalar 64-bit register and must be narrowed explicitly for guest addresses")
require("XOWUE_INPUT_POLL" in ENGINE and "XOWUE_INPUT_POLLED" in ENGINE,
        "guest polling and consumed state must remain observable")
require("XOWUE_INPUT_SUMMARY" in ENGINE,
        "exit diagnostics must preserve host updates and guest poll totals")
require("installXowueXamInputImports" not in ENGINE,
        "do not bypass the generated PPC import stub or its cancellation checkpoint")
require('title: playStationLayout ? "×" : "A"' in APP and
        "mask: XOWUEGamepadButton.a" in APP and
        'Text(playStationLayout ? "PS" : "XBOX")' in APP,
        "PlayStation cross must map to Xbox A and the layout must be selectable")

require("kXowueTouchControllerUserIndex = 0u" in ENGINE and
        "userIndex != kXowueTouchControllerUserIndex" in ENGINE,
        "one touch pad must map to exactly one Xbox user index")
require("reason=controller_not_connected" in ENGINE,
        "XAM/XInput must report unoccupied user slots as disconnected instead of mirroring one pad")
xinput_set = ENGINE[ENGINE.index("void xowue_XInputSetState("):
                    ENGINE.index("void xowue_XamInputSetState(")]
xam_set = ENGINE[ENGINE.index("void xowue_XamInputSetState("):
                  ENGINE.index("void xowue_VdQueryVideoFlags(")]
require("userIndex == kXowueTouchControllerUserIndex" in xinput_set and
        "userIndex == kXowueTouchControllerUserIndex" in xam_set,
        "XInput and XAM rumble must use the same connected-controller slot as GetState")

# XamInputGetKeystrokeEx has a different ABI from XamInputGetKeystroke:
# its first guest argument is a pointer to a USER_INDEX, updated on success.
# Verified against Xenia/ReXGlue:
# https://github.com/KoreanSeats1/Theft4/blob/main/glue/rexglue-sdk-main/src/kernel/xam/xam_input.cpp
keystroke_ex = ENGINE[ENGINE.index("void xowue_XamInputGetKeystrokeEx("):
                      ENGINE.index("void xowue_XInputGetCapabilities(")]
keystroke_core = ENGINE[ENGINE.index("static void xowue_XamInputGetKeystrokeImpl("):
                        ENGINE.index("void xowue_XamInputGetKeystroke(")]
keystroke_regular = ENGINE[ENGINE.index("void xowue_XamInputGetKeystroke("):
                           ENGINE.index("void xowue_XamInputGetKeystrokeEx(")]
require("const uint32_t userIndexAddress = context.r3.u32;" in keystroke_ex,
        "XamInputGetKeystrokeEx r3 must be treated as a pointer to USER_INDEX")
require("validGuestRange(userIndexAddress, 4u)" in keystroke_ex and
        "PPC_LOAD_U32(userIndexAddress)" in keystroke_ex,
        "XamInputGetKeystrokeEx must validate and dereference the guest USER_INDEX pointer")
require("userIndexAddress, userIndexAddress" in keystroke_ex,
        "XamInputGetKeystrokeEx must retain the caller pointer for successful write-back")
require("PPC_STORE_U32(userIndexWriteBackAddress, keystroke.userIndex)" in keystroke_core,
        "XamInputGetKeystrokeEx must write the selected user index back only after a key is dequeued")
require("if (userIndexWriteBackAddress != 0u)" in keystroke_core,
        "the ordinary GetKeystroke ABI must not write through its r3 user-index value")
require("const uint32_t requestedUserIndex = context.r3.u32;" in keystroke_regular,
        "XamInputGetKeystroke must continue to accept r3 as a direct user index")
require("xowueXamFlagsAllowGamepad(flags)" in keystroke_core,
        "both XAM keystroke APIs must reject unsupported device-type masks")

print("XOWUE_GENERATED_INPUT_IMPORTS_OK")


require("kXowueTouchControllerUserIndex = 0u" in ENGINE and
        "userIndex != kXowueTouchControllerUserIndex" in ENGINE,
        "one touch pad must map to exactly one Xbox user index")
require("reason=controller_not_connected" in ENGINE,
        "XAM/XInput must report unoccupied user slots as disconnected instead of mirroring one pad")
