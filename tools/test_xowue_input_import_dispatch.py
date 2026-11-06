#!/usr/bin/env python3
"""Verify XAM input imports are wired by the generated PPC runtime stubs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")
GENERATOR = (ROOT / "Runtime/generate_runtime_stubs.py").read_text(encoding="utf-8")

MAPPINGS = {
    "XInputGetState": "xowue_XInputGetState",
    "XamInputGetState": "xowue_XamInputGetState",
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

require("XOWUE_INPUT_POLL" in ENGINE and "XOWUE_INPUT_POLLED" in ENGINE,
        "guest polling and consumed state must remain observable")
require("XOWUE_INPUT_SUMMARY" in ENGINE,
        "exit diagnostics must preserve host updates and guest poll totals")
require("installXowueXamInputImports" not in ENGINE,
        "do not bypass the generated PPC import stub or its cancellation checkpoint")
print("XOWUE_GENERATED_INPUT_IMPORTS_OK")
