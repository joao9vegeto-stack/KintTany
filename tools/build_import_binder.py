#!/usr/bin/env python3
"""Validate PS3 HLE import manifest and generate strict guest stub/NID binder.

No ELF or game executable bytes are read or emitted. The input import table
may still be private; never upload title-specific output to public CI.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path

class ImportManifestError(ValueError):
    pass

def parse_uint32(v: object, label: str) -> int:
    try:
        if isinstance(v, bool):
            raise ValueError()
        val = int(v, 0) if isinstance(v, str) else int(v)
    except (TypeError, ValueError):
        raise ImportManifestError(f"invalid {label}") from None
    if val < 0 or val > 0xFFFFFFFF:
        raise ImportManifestError(f"{label} outside 32-bit unsigned range")
    return val

def validate(rows: object) -> tuple[list[dict],dict]:
    if not isinstance(rows, list) or not (1 <= len(rows) <= 2048):
        raise ImportManifestError("import list must contain 1..2048 entries")
    out = []
    used = set()
    by_lib = Counter()
    nids = set()
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ImportManifestError(f"entry {idx} is not an object")
        stub = parse_uint32(row.get("stub"), "stub")
        nid = parse_uint32(row.get("nid"), "nid")
        lib = row.get("library")
        if not stub or stub & 3 or not nid:
            raise ImportManifestError(f"entry {idx} has null or misaligned values")
        if not isinstance(lib, str) or not lib or len(lib) > 80 or not all(c.isalnum() or c in "._-" for c in lib):
            raise ImportManifestError(f"entry {idx}: invalid library label")
        if stub in used:
            raise ImportManifestError(f"duplicate guest stub 0x{stub:08x} (different NIDs not allowed)")
        used.add(stub); nids.add(nid); by_lib[lib] += 1
        out.append({"stub":stub, "nid":nid, "library":lib})
    out.sort(key=lambda v: v["stub"])
    return out, {
        "schema":"ascension-recomp/import-binder-v1",
        "stubs_validated":len(out),
        "unique_nids":len(nids),
        "by_library":dict(sorted(by_lib.items())),
        "note":"Guest stub addresses and NIDs only. No code, ELF bytes or licenses.",
    }

def generate(entries: list[dict]) -> str:
    code = [
        "/* Generated PS3 import stub binder. Title manifest remains private. */",
        '#include "ppu_bridge.h"',
        "int ar_register_guest_import_manifest(void) {",
        "  int rc;",
    ]
    for row in entries:
        code.append(f'  rc = ar_bind_import(0x{row["stub"]:08x}u, 0x{row["nid"]:08x}u);')
        code.append("  if (rc != AR_OK) return rc;")
    code.extend(["  return AR_OK;","}",""])
    return "\n".join(code)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--imports",type=Path,required=True)
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    entries, report=validate(json.loads(args.imports.read_text(encoding="utf-8")))
    args.source.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.source.write_text(generate(entries),encoding="utf-8")
    args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Validated guest import stubs: {len(entries)}; unique firmware NIDs: {report['unique_nids']}")
    print("Compiled source is DATA-DERIVED. Keep local, never commit commercial-title bindings.")

if __name__=="__main__":
    main()
