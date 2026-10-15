#!/usr/bin/env python3
"""Trim loader function end addresses to actual executable ELF sections."""
import argparse
import json
from pathlib import Path

def sanitize(functions,sections):
    spans=sorted((int(s["address"],0),int(s["end"],0)) for s in sections)
    if not spans or any(b<=a for a,b in spans):
        raise ValueError("invalid executable sections")
    if any(a[1]>b[0] for a,b in zip(spans,spans[1:])):
        raise ValueError("overlapping executable sections")
    fixed=[]
    repairs=[]
    for item in functions:
        s,e=int(item["start"],0),int(item["end"],0)
        section=next(((a,b) for a,b in spans if a<=s<b),None)
        if section is None or s%4 or e%4 or e<=s:
            raise ValueError("invalid function start/end or outside executable section")
        lim=min(e,section[1])
        out=dict(item)
        out["end"]=hex(lim)
        fixed.append(out)
        if lim != e:
            repairs.append({"start":hex(s),"old_end":hex(e),"new_end":hex(lim),"invalid_tail_bytes_removed":e-lim})
    return fixed,repairs

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--functions",type=Path,required=True)
    p.add_argument("--audit",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    fs=json.loads(a.functions.read_text())
    audit=json.loads(a.audit.read_text())
    fixed,repairs=sanitize(fs,audit["executable_sections"])
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(fixed,indent=1)+"\n")
    a.report.write_text(json.dumps({"schema":"ascension-recomp/ppu-boundaries-v1",
        "functions_input":len(fs),"functions_output":len(fixed),
        "clipped_intervals":len(repairs),
        "invalid_tail_bytes_removed":sum(x["invalid_tail_bytes_removed"] for x in repairs),
        "repairs":repairs},indent=2)+"\n")
    print("Preserved",len(fixed),"function starts; clipped",len(repairs),"invalid ranges")

if __name__=="__main__":
    main()
