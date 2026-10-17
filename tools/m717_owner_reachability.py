#!/usr/bin/env python3
"""M7.17 PRIVATE owner's PPC64 call-graph inventory and AOT batch candidate plan.

Never uploads or bundles commercial ELF. Static edges are POSSIBLE paths only.
Accepted candidates use the project's existing STRICT bounded AOT lifter.
This is not a full recompiler and does not produce gameplay on its own.
"""
from __future__ import annotations
import argparse
import json
import re
import struct
from pathlib import Path
from collections import deque
from ppu_cfg_lifter import PPUImage, Unsupported
from m714_owner_batch import plan

MAX_NODES = 100_000
MAX_CANDIDATES = 8192

def signed_disp(w: int, mask: int, sign: int, modulus: int) -> int:
    n = w & mask
    return n - modulus if n & sign else n

def discover(image, roots: list[int], max_nodes: int = 20000) -> dict:
    if not 1 <= max_nodes <= MAX_NODES or not 1 <= len(roots) <= 256:
        raise ValueError("invalid discovery budget/seeds")
    queue = deque()
    scheduled = set()
    for pc in roots:
        if not isinstance(pc, int) or pc <= 0 or pc > 0xffffffff or pc & 3:
            raise ValueError("unaligned/invalid root")
        if pc not in scheduled:
            queue.append(pc)
            scheduled.add(pc)
    visited = set()
    candidate_calls = set()
    counters = dict(direct_calls=0, conditional=0, indirect=0,
                    syscalls=0, invalid_pc=0, edges=0)
    def add(target):
        if 0 < target <= 0xffffffff and target & 3 == 0 and target not in scheduled:
            scheduled.add(target)
            queue.append(target)
    while queue and len(visited) < max_nodes:
        pc = queue.popleft()
        try:
            w = image.words(pc, pc + 4)[0]
        except (Unsupported, IndexError, ValueError):
            counters["invalid_pc"] += 1
            continue
        visited.add(pc)
        op = w >> 26
        if op == 18:
            offset = signed_disp(w,0x3fffffc,0x2000000,0x4000000)
            dest = offset if w & 2 else pc + offset
            add(dest)
            counters["edges"] += 1
            if w & 1:
                counters["direct_calls"] += 1
                if 0 < dest <= 0xffffffff and dest & 3 == 0:
                    try:
                        image.words(dest, dest + 4)
                        candidate_calls.add(dest)
                    except Unsupported:
                        pass
                add(pc + 4)
                counters["edges"] += 1
        elif op == 16:
            offset = signed_disp(w,0xfffc,0x8000,0x10000)
            dest = offset if w & 2 else pc + offset
            add(dest)
            add(pc+4)
            counters["conditional"] += 1
            counters["edges"] += 2
        elif op == 19 and (w >> 1) & 1023 in (16, 528):
            counters["indirect"] += 1
            bo = (w >> 21) & 31
            if bo & 20 != 20:
                add(pc+4)
                counters["edges"] += 1
        else:
            if op == 17:
                counters["syscalls"] += 1
            add(pc+4)
            counters["edges"] += 1
    return {"schema":"ascensionrecomp/m717-bounded-callgraph",
            "roots":[f"0x{x:08x}" for x in roots],
            "nodes_inspected":len(visited),"queued":len(scheduled),
            "truncated":bool(queue),"possible_edges":counters,
            "direct_call_candidates":[f"0x{x:08x}" for x in sorted(candidate_calls)],
            "note":"Potential edges, not actual execution, not validated whole functions."}

def report_seeds(text: str) -> list[int]:
    # Extract only explicit authenticated PCs and direct call targets.
    patterns = (r"CALL_CANDIDATE\s+0x([0-9a-fA-F]{8})",
                r"Próximo bloco sem ARM64:\s*0x([0-9a-fA-F]{8})",
                r"PC inicial=0x([0-9a-fA-F]{8})")
    return sorted({int(m,16) for pat in patterns for m in re.findall(pat,text)})

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--elf",type=Path,required=True)
    cli.add_argument("--out",type=Path,required=True)
    cli.add_argument("--report",type=Path,help="Optional pasted iPhone AOT/batch report")
    cli.add_argument("--root",action="append",default=[],
                     help="Additional verified PPC PC (e.g. 0x003c4e14)")
    cli.add_argument("--max-nodes",type=int,default=20000)
    cli.add_argument("--max-functions",type=int,default=1024)
    cli.add_argument("--max-words",type=int,default=256)
    args=cli.parse_args()
    if not 1<=args.max_functions<=MAX_CANDIDATES:
        cli.error("max-functions out of bounds")
    if not 1<=args.max_words<=512:
        cli.error("max-words out of bounds")
    image=PPUImage(args.elf)
    entry=struct.unpack_from(">Q",image.blob,24)[0]
    roots=[entry]+[int(x,0) for x in args.root]
    if args.report:
        roots+=report_seeds(args.report.read_text())
    roots=list(dict.fromkeys(roots))
    graph=discover(image,roots,args.max_nodes)
    candidates=[int(x,16) for x in graph["direct_call_candidates"]]
    seeds=list(dict.fromkeys([*roots,*candidates]))[:args.max_functions]
    audit=plan(image,seeds,args.max_words)
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"callgraph-audit.json").write_text(json.dumps(graph,indent=2)+"\n")
    (args.out/"aot-candidates-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    functions=[{"start":x["start"],"end":x["end"]} for x in audit["accepted"]]
    (args.out/"candidate-functions.json").write_text(json.dumps(functions,indent=2)+"\n")
    print("M7.17 private PPC graph:",graph["nodes_inspected"],
          "verified executable words; potential calls:",len(candidates))
    print("Strict native AOT function candidates:",len(functions),
          "rejected:",len(audit["rejected"]))
    print("Not a drop-in secret: owner must merge previously linked entries")
    print("and rebuild the COMPLETE private native AOT bundle before deployment.")

if __name__=="__main__":
    main()
