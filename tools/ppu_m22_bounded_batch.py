#!/usr/bin/env python3
"""Bounded, fail-closed experimental PPU function audit. Never publish generated game code."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppu_lift_probe import UnsupportedOpcode, lift_words, read_ppu_words

def audit(elf: Path, functions: list, output: Path, max_instructions: int = 256) -> dict:
    if not 1 <= max_instructions <= 256:
        raise ValueError("strict maximum is 1..256")
    output.mkdir(parents=True, exist_ok=True)
    rejects = Counter()
    accepted = []
    names = set()
    for f in functions:
        try:
            start, end = int(str(f["start"]), 0), int(str(f["end"]), 0)
            if start in names:
                raise ValueError("duplicate function start")
            names.add(start)
            if start % 4 or end % 4 or end <= start:
                raise ValueError("misaligned/empty function interval")
            count = (end-start)//4
            if count > max_instructions:
                raise ValueError("function exceeds instruction bound")
            words = read_ppu_words(elf, start, count)
            if words[-1] != 0x4e800020:
                raise ValueError("declared range does not end in BLR")
            src, ops = lift_words(words, start)
            if len(ops) != count:
                raise ValueError("premature BLR: incomplete function")
            name = f"ar_func_{start:08x}"
            src = src.replace("int ar_lifted_entry(", f"int {name}(", 1)
            (output/f"{name}.c").write_text(src, encoding="utf-8")
            accepted.append({"entry": hex(start), "instructions": count, "file": name+".c"})
        except (ValueError, KeyError, TypeError, UnsupportedOpcode, IndexError) as err:
            rejects[str(err).split(" at 0x")[0]] += 1
    return {"schema":"ascension-recomp/m22-bounded-aot-audit-v1",
            "input_count":len(functions),"accepted_count":len(accepted),
            "rejected_count":sum(rejects.values()),"reasons":dict(rejects.most_common()),
            "accepted":accepted,
            "note":"Limited subset with early return rejection. Not proof of runtime/gameplay."}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("elf",type=Path)
    ap.add_argument("--functions",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--max-instructions",type=int,default=256)
    args=ap.parse_args()
    rows=json.loads(args.functions.read_text(encoding="utf-8"))
    if not isinstance(rows,list):
        ap.error("functions must be a JSON array")
    report=audit(args.elf,rows,args.output,args.max_instructions)
    (args.output/"audit.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"strict bounded AOT: {report['accepted_count']} accepted, {report['rejected_count']} rejected")
    return 0 if report["accepted_count"] else 2

if __name__=="__main__":
    raise SystemExit(main())
