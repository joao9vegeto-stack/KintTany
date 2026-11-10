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
    0x82574348,  # virtual stream-provider read submission callback (observed in Build 138)
    0x82573CB0,  # implementation behind the observed 0x82574348 wrapper
    0x824A7DF0,  # async stream service interface getter used by the observed callsite
    0x8257D290,  # stream provider's request enqueue/dispatch implementation
    0x822A0608,  # request descriptor preparation immediately before enqueue
    0x82573620,  # async stream-manager setup/use path
    0x82573AE8,  # async stream-manager setup/use path
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
                "stream_dispatch_calls":["0x825753D0","0x82575474"],
                "observed_submission_callback":"0x82574348",
                "observed_submission_implementation":"0x82573CB0",
                "observed_service_getter":"0x824A7DF0",
                "observed_request_enqueue":"0x8257D290",
                "observed_request_prepare":"0x822A0608",
                "observed_submission_site":"0x82575244",
                "expected_completion_site":"0x82575474"
            }}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("XOWUE_STREAM_SUPPORT_AOT_SOURCE "+json.dumps({
        "found":[{"name":f["name"],"file":f["file"],
                  "instruction_comments":f["instruction_comment_count"],
                  "body_chars":len(f["body"])} for f in result["functions"]],
        "missing":missing}))
    required=(0x82575480,0x82575108,0x82574348,0x82573CB0,0x824A7DF0,0x8257D290,0x822A0608)
    missing_required=[f"0x{x:08X}" for x in required if x not in found]
    if missing_required:
        raise SystemExit("Required stream poll / callback source missing: "+", ".join(missing_required))

if __name__=="__main__": main()
