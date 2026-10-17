#!/usr/bin/env python3
"""Verify real DEFINED owner AOT entrypoints in the FINAL iPhoneOS Mach-O.

Never trust source strings, undefined symbols or object-only nm listings.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
from stage_m78_aot import EXPECTED_SYMBOLS, M712_NEXT_PC

AOT_PATTERN = re.compile(r"ar_game_ppu_[0-9a-f]{8}\Z")


def verify(nm_text: str, manifest_text: str, expected_count: int) -> int:
    names = manifest_text.splitlines()
    required = set(EXPECTED_SYMBOLS) | {M712_NEXT_PC}
    if len(names) != expected_count or not 60 <= len(names) <= 8192:
        raise ValueError("M7.12 source manifest has wrong number of entrypoints")
    if len(set(names)) != len(names) or not all(AOT_PATTERN.fullmatch(x) for x in names):
        raise ValueError("M7.12 source manifest has duplicates/invalid symbols")
    if not required.issubset(set(names)):
        raise ValueError("M7.12 source manifest lost 59 previous entries or missing PC")
    defined: list[str] = []
    for line in nm_text.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[-2] not in ("T", "t"):
            continue
        sym = fields[-1]
        if sym.startswith("_") and AOT_PATTERN.fullmatch(sym[1:]):
            defined.append(sym[1:])
    if len(defined) != len(set(defined)) or set(defined) != set(names):
        missing = set(names) - set(defined)
        extra = set(defined) - set(names)
        raise ValueError(
            "M7.12 iPhoneOS Mach-O code symbol mismatch: "
            f"missing={len(missing)} extra={len(extra)} duplicate={len(defined) - len(set(defined))}"
        )
    return len(defined)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("nm_file", type=Path)
    p.add_argument("manifest_file", type=Path)
    p.add_argument("expected_count", type=int)
    args = p.parse_args()
    count = verify(args.nm_file.read_text(), args.manifest_file.read_text(), args.expected_count)
    print(f"M7.12 Mach-O verified: {count} original PPC entrypoints defined in ARM64 executable, including 0x002C1664")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
