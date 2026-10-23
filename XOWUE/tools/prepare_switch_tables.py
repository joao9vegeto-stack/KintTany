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
    tables = parsed.get("switch", [])
    if any(table["base"] == FUNCTION_DISPATCH_TABLE for table in tables):
        raise AssertionError("Filtered dispatch table remains in output")
    if removed not in (0, 1):
        raise ValueError(f"Expected to filter at most one table, filtered {removed}")
    if removed == 0 and len(tables) != 36:
        raise ValueError(
            f"No table was filtered and output contains {len(tables)} switches; "
            "the input may not be the expected XOWUE analysis"
        )
    if removed == 1 and len(tables) != 36:
        raise ValueError(f"Expected 36 curated switches, found {len(tables)}")

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
