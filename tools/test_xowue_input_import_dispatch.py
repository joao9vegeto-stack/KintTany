#!/usr/bin/env python3
"""Regression checks for real XAM input import dispatch in XOWUE."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")

ORDINALS = {
    "GetCapabilities": "0190",
    "GetState": "0191",
    "SetState": "0192",
    "GetCapabilitiesEx": "02AD",
}

def require(condition, message):
    if not condition:
        raise AssertionError(message)

for suffix, ordinal in ORDINALS.items():
    require(f"constexpr uint16_t kXowueXamInput{suffix}Ordinal = 0x{ordinal}u;" in ENGINE,
            f"XamInput{suffix} ordinal must match Xenia's XAM export table")
    require(f"handler = &xowue_XamInput{suffix};" in ENGINE,
            f"XamInput{suffix} must be registered to its native handler")

require('normalized == "xam.xex"' in ENGINE, "XEX parser must identify xam.xex imports")
require("thunk->originalData.type == 0u" in ENGINE, "data imports must remain distinct from function imports")
require("g_xowueXamInputImports.push_back({firstThunk, ordinal});" in ENGINE,
        "XAM function import thunk addresses must be retained")
require("installXowueXamInputImports(*memory);" in ENGINE,
        "XAM import patching must run after AOT dispatch installation")
require("mapping->second = handler;" in ENGINE, "host AOT lookup must point at the native XAM handler")
require("*slot = handler;" in ENGINE, "guest AOT dispatch slot must point at the native XAM handler")
require("XOWUE_INPUT_IMPORT_PATCH_SUMMARY" in ENGINE, "runtime must report registered input handlers")
require("XOWUE_INPUT_POLL" in ENGINE and "XOWUE_INPUT_POLLED" in ENGINE,
        "guest-side polling and consumed state must remain observable")
print("XOWUE_XAM_INPUT_IMPORT_DISPATCH_OK")
