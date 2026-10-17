#!/usr/bin/env python3
"""Assert all owner-secret M7.18 bulk functions are defined as ARM64 code.

No bulk source, commercial ELF or secret value is printed or uploaded.
"""
import re
import sys
from pathlib import Path

def verify(text: str, expected_names: list[str], count: int) -> int:
    actual=set(re.findall(r"\b[Tt]\s+_?(ar_bulk_ppu_[0-9a-f]{8})\s*$",text,re.M))
    if count!=500 or len(expected_names)!=count or len(set(expected_names))!=count:
        raise ValueError("M7.18 expected 500 unique functions")
    if any(not re.fullmatch(r"ar_bulk_ppu_[0-9a-f]{8}",x) for x in expected_names):
        raise ValueError("M7.18 invalid native symbol")
    missing=set(expected_names)-actual
    if missing or len(actual)!=count:
        raise ValueError(f"M7.18 linked ARM64 native symbols missing={len(missing)}, found={len(actual)}")
    return count

def main():
    if len(sys.argv)!=4:raise ValueError("usage: symbols.txt manifest.txt count")
    symbols=Path(sys.argv[1]).read_text()
    required=Path(sys.argv[2]).read_text().splitlines()
    n=verify(symbols,required,int(sys.argv[3]))
    print(f"M7.18 verified {n} additional game PPC AOT functions defined in ARM64 Mach-O")

if __name__=="__main__":
    try:main()
    except (ValueError,OSError) as error:
        print("M7.18 verification rejected: "+str(error),file=sys.stderr)
        sys.exit(1)
