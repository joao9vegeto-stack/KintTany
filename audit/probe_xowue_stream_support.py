#!/usr/bin/env python3
"""Extract supporting generated AOT functions for the Wolverine stream poll loop."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

FUNC = re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{')
COMMENT = re.compile(r'(?m)^\s*//\s+(.+?)\s*$')
OWNERS = (
    0x82495BF8,  # caller which asks for the stream bytes
    0x82575250,  # stream range / chunk update callback
    0x82575480,  # polling wrapper with vtable completion loop
    0x82575108,  # chunk request helper
    0x822A0160,  # stream metadata helper
    0x822A00C0,  # stream metadata helper
    0x82C3C4D8,  # timebase helper
    0x82C3EE78,  # wait/yield helper
    0x82C2A290,  # buffer copy / advance helper
)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ppc-dir",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    wanted=set(OWNERS)
    found={}
    for file in sorted(args.ppc_dir.glob("ppc_recomp.*.cpp")):
        src=file.read_text("utf-8")
        entries=list(FUNC.finditer(src))
        for i,entry in enumerate(entries):
            owner=int(entry.group(1)[4:],16)
            if owner not in wanted: continue
            end=entries[i+1].start() if i+1<len(entries) else len(src)
            body=src[entry.end():end]
            found[owner]={"name":f"sub_{owner:08X}","file":file.name,
                          "instruction_comment_count":len(COMMENT.findall(body)),
                          "body":body}
    missing=[f"0x{x:08X}" for x in OWNERS if x not in found]
    result={"purpose":"Verbatim generated AOT bodies for stream polling and read completion investigation.",
            "functions":[found[x] for x in OWNERS if x in found],
            "missing":missing,
            "important_runtime_call_sites":{
                "outer_vtable_call":"0x82495C60",
                "inner_vtable_call":"0x8257550C",
                "inner_return_test":"0x82575510",
                "inner_retry_branch":"0x82575514",
                "yield_call":"0x825754F0",
                "stream_dispatch_calls":["0x825753D0","0x82575474"]
            }}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("XOWUE_STREAM_SUPPORT_AOT_SOURCE "+json.dumps({
        "found":[{"name":f["name"],"file":f["file"],
                  "instruction_comments":f["instruction_comment_count"],
                  "body_chars":len(f["body"])} for f in result["functions"]],
        "missing":missing}))
    if 0x82575480 not in found or 0x82575108 not in found:
        raise SystemExit("Required stream poll / chunk helper source missing")

if __name__=="__main__": main()
