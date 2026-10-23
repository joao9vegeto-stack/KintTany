#!/usr/bin/env python3
"""Pack generated PPC translation units and split them for Git storage."""
from __future__ import annotations
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PPC_DIR = ROOT / "generated" / "ppc"
DIST = ROOT / "dist"
ARCHIVE = DIST / "XOWUE-AOT-source.tar.gz"
PART_PREFIX = DIST / "XOWUE-AOT-source.part"
PART_SIZE = 4 * 1024 * 1024


def main() -> int:
    if not (PPC_DIR / "ppc_recomp_shared.h").is_file():
        raise SystemExit(f"missing generated AOT tree: {PPC_DIR}")
    units = sorted(PPC_DIR.glob("ppc_recomp.*.cpp"))
    if len(units) != 344 or not (PPC_DIR / "ppc_func_mapping.cpp").is_file():
        raise SystemExit("expected 344 function units and ppc_func_mapping.cpp")

    DIST.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "-czf", str(ARCHIVE), "-C", str(ROOT / "generated"), "ppc"], check=True)
    data = ARCHIVE.read_bytes()
    old_parts = sorted(DIST.glob("XOWUE-AOT-source.part[0-9][0-9]"))
    for part in old_parts:
        part.unlink()
    parts = []
    for index, offset in enumerate(range(0, len(data), PART_SIZE)):
        path = Path(f"{PART_PREFIX}{index:02d}")
        path.write_bytes(data[offset:offset + PART_SIZE])
        parts.append(path)
    digest = hashlib.sha256(data).hexdigest()
    (DIST / "SHA256SUMS").write_text(
        f"{digest}  dist/XOWUE-AOT-source.tar.gz\n", encoding="utf-8"
    )
    print(f"packed {len(units) + 1} generated C++ units into {ARCHIVE}")
    print(f"split archive into {len(parts)} parts of at most {PART_SIZE} bytes")
    print(f"sha256 {digest}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
