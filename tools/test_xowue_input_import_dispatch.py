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
print("XOWUE_GENERATED_INPUT_IMPORTS_OK")
