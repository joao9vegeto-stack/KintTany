#!/usr/bin/env python3
"""Require all 850 owner-private M7.19 guest entrypoints as defined ARM64 code."""
from __future__ import annotations
import re
import sys
from pathlib import Path

COUNT=850

def verify(symbols: str, names: list[str], expected: int = COUNT) -> int:
    code=set(re.findall(r"\b[Tt]\s+_?(ar_bulk2_ppu_[0-9a-f]{8})\s*$",symbols,re.M))
    if expected!=COUNT or len(names)!=COUNT or len(set(names))!=COUNT:
        raise ValueError("M7.19 manifest count/uniqueness invalid")
    if any(not re.fullmatch(r"ar_bulk2_ppu_[0-9a-f]{8}",n) for n in names):
        raise ValueError("M7.19 malformed native symbol")
    missing=set(names)-code
    if missing or len(code)!=COUNT:
        raise ValueError(f"M7.19 Mach-O has {len(code)} native guest entries, {len(missing)} missing")
    return COUNT

if __name__=="__main__":
    try:
        if len(sys.argv)!=4:
            raise ValueError("usage: symbols.txt manifest.txt count")
        n=verify(Path(sys.argv[1]).read_text(),
                 Path(sys.argv[2]).read_text().splitlines(),
                 int(sys.argv[3]))
        print(f"M7.19 verified {n} NEW original PPC basic blocks in ARM64 Mach-O")
    except (ValueError,OSError) as exc:
        print("M7.19 AOT verification failed: "+str(exc),file=sys.stderr)
        sys.exit(1)
