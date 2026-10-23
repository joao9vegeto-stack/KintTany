#!/usr/bin/env python3
"""Curate XenonAnalyse jump tables for the XOWUE recompilation."""
from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

FUNCTION_DISPATCH_TABLE = 0x82BD174C
EXPECTED_LABELS = {
    0x82BD1774,
    0x82BD1784,
    0x82BD1794,
    0x82BD17A8,
    0x82BD17B8,
    0x82BD17C8,
    0x82BD17D8,
    0x82BD17E8,
}
MANUAL_SWITCH = {
    "base": 0x8237CA50,
    "r": 11,
    "default": 0x8237CB40,
    "labels": [
        0x8237CAD0,
        0x8237CADC,
        0x8237CAE8,
        0x8237CAF4,
        0x8237CB00,
        0x8237CB00,
        0x8237CB08,
        0x8237CB14,
        0x8237CB20,
        0x8237CB2C,
        0x8237CB38,
    ],
}


def curate(source: Path, destination: Path) -> tuple[int, int]:
    original = source.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^\[\[switch\]\]\s*$)", original, flags=re.MULTILINE)
    if not blocks or "[[switch]]" not in original:
        raise ValueError(f"No [[switch]] tables found in {source}")

    kept = [blocks[0]]
    removed = 0
    for block in blocks[1:]:
        match = re.search(r"^base\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)\s*$", block, re.MULTILINE)
        if not match:
            raise ValueError("Found a switch block without a parseable base address")
        base = int(match.group(1), 0)
        if base == FUNCTION_DISPATCH_TABLE:
            parsed = tomllib.loads(block)
            table = parsed["switch"][0]
            actual_labels = set(table.get("labels", []))
            if actual_labels != EXPECTED_LABELS:
                raise ValueError(
                    "The function-dispatch table changed; inspect it before filtering. "
                    f"Expected {[hex(x) for x in sorted(EXPECTED_LABELS)]}, "
                    f"got {[hex(x) for x in sorted(actual_labels)]}"
                )
            removed += 1
            continue
        kept.append(block)

    text = "".join(kept)
    parsed = tomllib.loads(text)
    if any(table["base"] == MANUAL_SWITCH["base"] for table in parsed.get("switch", [])):
        raise ValueError(f"Manual switch table 0x{MANUAL_SWITCH['base']:08X} already exists")
    text = text.rstrip() + "\n\n# Manually verified reordered absolute table\n[[switch]]\n"
    text += f"base = 0x{MANUAL_SWITCH['base']:08X}\nr = {MANUAL_SWITCH['r']}\n"
    text += f"default = 0x{MANUAL_SWITCH['default']:08X}\nlabels = [\n"
    text += "".join(f"    0x{label:08X},\n" for label in MANUAL_SWITCH["labels"])
    text += "]\n"
    parsed = tomllib.loads(text)
    tables = parsed.get("switch", [])
    if any(table["base"] == FUNCTION_DISPATCH_TABLE for table in tables):
        raise AssertionError("Filtered dispatch table remains in output")
    if removed not in (0, 1):
        raise ValueError(f"Expected to filter at most one table, filtered {removed}")
    if len(tables) != 37:
        raise ValueError(f"Expected 37 curated switches including the manual table, found {len(tables)}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return len(tables), removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="XenonAnalyse TOML file")
    parser.add_argument("output", type=Path, help="Curated TOML output")
    args = parser.parse_args()
    count, removed = curate(args.input, args.output)
    print(f"Curated {count} switch tables; removed {removed} function-dispatch table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())