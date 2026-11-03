#!/usr/bin/env python3
"""Audit source-matched XEX switch callsites skipped by the generic AOT lowering pass."""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter
from pathlib import Path

FUNC = re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]+)\) \{\n')
INSN = re.compile(r'(?m)^\t// (.+?)\s*$')

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ppc-dir", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    source_report = json.loads(a.report.read_text())
    gaps = [int(x["branch"], 16) for x in source_report.get("details", [])
            if x.get("reason") == "guarded_AOT_callsite_absent"]
    units = sorted(a.ppc_dir.glob("ppc_recomp.*.cpp"))
    matches = []
    for file in units:
        text = file.read_text()
        for m in FUNC.finditer(text):
            owner = int(m.group(1)[4:], 16)
            end = text.find("\n}\n", m.end())
            if end < 0:
                continue
            body = text[m.start():end + 3]
            ins = list(INSN.finditer(body))
            starts = [x.start() for x in ins]
            for pc in gaps:
                delta = pc - owner
                if delta < 0 or delta & 3:
                    continue
                idx = delta // 4
                if idx >= len(ins) or ins[idx].group(1).strip().lower() != "bctr":
                    continue
                start = ins[idx].end()
                stop = ins[idx + 1].start() if idx + 1 < len(ins) else len(body)
                chunk = body[start:stop]
                if "PPC_CALL_INDIRECT_FUNC" in chunk:
                    classification = "guarded_indirect_still_present"
                elif "switch (" in chunk or "goto loc_" in chunk:
                    classification = "already_native_control_flow"
                else:
                    classification = "unclassified_bctr_body"
                matches.append({
                    "branch": f"0x{pc:08X}",
                    "owner": f"0x{owner:08X}",
                    "source": file.name,
                    "classification": classification,
                    "snippet": chunk.strip()[:1600],
                })
    counts = Counter(x["classification"] for x in matches)
    report = {
        "generic_pass_skipped": len(gaps),
        "native_bctr_matches": len(matches),
        "unmatched": [f"0x{x:08X}" for x in gaps
                      if sum(y["branch"] == f"0x{x:08X}" for y in matches) == 0],
        "classification_counts": dict(counts),
        "details": matches,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2))
    print("XOWUE_GLOBAL_CALLSITE_AUDIT " + json.dumps({
        k: v for k, v in report.items() if k != "details"
    }))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
