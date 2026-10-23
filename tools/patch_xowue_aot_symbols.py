#!/usr/bin/env python3
"""Make the archived XOWUE AOT guest aliases strong before compiling them."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

SOURCE_SUFFIXES = {".h", ".hpp", ".hh", ".cpp", ".cc", ".cxx"}
WEAK_ATTRIBUTE = re.compile(r"__attribute__\(\(\s*weak\s*,\s*")
GUEST_SYMBOL = re.compile(r"sub_[0-9A-Fa-f]{8}")


def remove_weak_linkage(root: Path) -> tuple[int, int]:
    changed_files = 0
    replacements = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        updated_lines = []
        file_replacements = 0
        for line in source.splitlines(keepends=True):
            is_alias_macro = "PPC_WEAK_FUNC" in line and line.lstrip().startswith("#")
            is_guest_alias = GUEST_SYMBOL.search(line) is not None
            if is_alias_macro or is_guest_alias:
                line, count = WEAK_ATTRIBUTE.subn("__attribute__((", line)
                file_replacements += count
            updated_lines.append(line)

        if file_replacements:
            path.write_text("".join(updated_lines), encoding="utf-8")
            changed_files += 1
            replacements += file_replacements

    if replacements == 0:
        candidates = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
                try:
                    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                        if "PPC_WEAK_FUNC" in line or (GUEST_SYMBOL.search(line) and "weak" in line):
                            candidates.append(f"{path}:{number}:{line.strip()}")
                except UnicodeDecodeError:
                    pass
        detail = "\n".join(candidates[:20]) or "no generated PPC alias declaration found"
        raise SystemExit(f"no weak AOT alias declaration was patched under {root}\n{detail}")

    remaining = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        try:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if ("PPC_WEAK_FUNC" in line and line.lstrip().startswith("#") and "weak" in line) or (
                    GUEST_SYMBOL.search(line) and WEAK_ATTRIBUTE.search(line)
                ):
                    remaining.append(f"{path}:{number}:{line.strip()}")
        except UnicodeDecodeError:
            pass
    if remaining:
        raise SystemExit("weak AOT aliases remain after patch:\n" + "\n".join(remaining[:20]))
    return changed_files, replacements


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppc-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.ppc_dir.is_dir():
        raise SystemExit(f"missing archived AOT source directory: {args.ppc_dir}")
    changed_files, replacements = remove_weak_linkage(args.ppc_dir)
    print(
        f"XOWUE AOT linkage normalized: {replacements} weak alias attribute(s) "
        f"removed across {changed_files} archived source file(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
