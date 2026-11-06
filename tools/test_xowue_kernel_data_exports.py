#!/usr/bin/env python3
"""Regression checks for Xbox 360 kernel data-variable exports in XOWUE."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "Runtime" / "XOWUEEngine.cpp").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "xowue-ios.yml").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    parser_start = SOURCE.index("static void captureXowueKernelDataImportSites")
    parser_end = SOURCE.index("Image parseImage(const char *path)", parser_start)
    parser = SOURCE[parser_start:parser_end]

    require("XEX_HEADER_IMPORT_LIBRARIES" in parser, "XEX import-library header is not scanned")
    require('"xboxkrnl.exe"' in parser, "kernel import library is not selected")
    require("originalData.type != 0u" in parser, "function imports are not excluded from data import scan")
    require("kXowueKeTimeStampBundleOrdinal" in parser, "KeTimeStampBundle ordinal is not discovered")
    require("kXowueKeDebugMonitorDataOrdinal" in parser, "KeDebugMonitorData ordinal is not discovered")
    require("image.Find(firstThunk)" in parser, "variable import thunk is not resolved against loaded image")

    require("installXowueKernelDataExports(memory->base);" in SOURCE,
            "kernel data exports are not installed after copying the XEX")
    require("storeGuestBe32(base, g_xowueTimeStampBundleImportSite, address)" in SOURCE,
            "KeTimeStampBundle pointer slot is not populated")
    require("storeGuestBe32(base, g_xowueDebugMonitorDataImportSite, zeroWord)" in SOURCE,
            "KeDebugMonitorData pointer slot is not populated")
    require("116444736000000000ull" in SOURCE, "system time is not converted to Windows FILETIME")
    require("elapsedNs / 100u" in SOURCE and "elapsedNs / 1000000ull" in SOURCE,
            "interrupt time and millisecond tick fields are not populated")
    require('api == "GetTickCount" || api == "XamGetTickCount"' in SOURCE,
            "GetTickCount import is not implemented")
    require("updateXowueKernelTimeStampBundle(memory->base);" in SOURCE,
            "time stamp bundle is not updated during guest timebase reads")
    require("test_xowue_kernel_data_exports.py" in WORKFLOW,
            "CI does not execute the kernel data export regression test")
    print("XOWUE Xbox 360 kernel data-variable exports: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
