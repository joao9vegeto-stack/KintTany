#!/usr/bin/env python3
"""Cross-reference unresolved GOW3 PS4 NIDs with shadPS4's HLE export registry.
This is a naming/reference audit only. No shadPS4 emulator code is linked or executed.
A match does not mean its implementation is suitable for the native iOS runtime.
"""
from __future__ import annotations
import argparse
import collections
import json
import re
from pathlib import Path

EXPORT = re.compile(
    r'LIB_FUNCTION\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*[^,]+,\s*"([^"]+)"\s*,\s*([A-Za-z_][A-Za-z_0-9:]*)',
    re.MULTILINE | re.DOTALL,
)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--linked", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    linked = json.loads(args.linked.read_text())
    unresolved = linked.get("unresolved_imports")
    if not isinstance(unresolved, list):
        raise SystemExit("link.json has no unresolved_imports list")
    exports = collections.defaultdict(list)
    files = sorted(args.source.rglob("*.cpp"))
    if not files:
        raise SystemExit("No shadPS4 library source files found")
    for path in files:
        source = path.read_text(errors="ignore")
        for match in EXPORT.finditer(source):
            nid, library_alias, module, function = match.groups()
            exports[f"{nid}#{module}"].append({
                "function": function,
                "library_alias": library_alias,
                "source": str(path.relative_to(args.source.parent.parent.parent.parent)),
            })
    matched, missing = [], []
    by_module = collections.Counter()
    for name in sorted(set(unresolved)):
        if "#" not in name:
            missing.append({"import": name, "reason": "invalid import identity"})
            continue
        nid, module = name.rsplit("#", 1)
        candidates = exports.get(name, [])
        if candidates:
            matched.append({"import": name, "nid": nid, "module": module, "candidates": candidates})
            by_module[module] += 1
        else:
            missing.append({"import": name, "nid": nid, "module": module})
    report = {
        "reference": "shadPS4 HLE LIB_FUNCTION registry; names only, not runtime reuse",
        "shadps4_commit": args.commit,
        "source_files_scanned": len(files),
        "unique_unresolved_imports": len(set(unresolved)),
        "matched_imports": len(matched),
        "unmatched_imports": len(missing),
        "matched_by_module": dict(sorted(by_module.items())),
        "matches": matched,
        "unmatched": missing,
        "policy": "A NID name match is a research lead, not a safe stub or an implementation. Every used import still needs a native PS4 ABI-compatible iOS service and tests.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in (
        "shadps4_commit", "source_files_scanned", "unique_unresolved_imports",
        "matched_imports", "unmatched_imports", "matched_by_module"
    )}, indent=2))

if __name__ == "__main__":
    main()
