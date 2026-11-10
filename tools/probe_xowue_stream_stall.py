#!/usr/bin/env python3
"""Evidence-only extraction of native AOT source for Wolverine startup stream stall."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

FUNC = re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{')
COMMENT = re.compile(r'(?m)^\s*//\s+(.+?)\s*$')

def records(ppc_dir: Path):
    for file in sorted(ppc_dir.glob("ppc_recomp.*.cpp")):
        source=file.read_text("utf-8")
        entries=list(FUNC.finditer(source))
        for i, entry in enumerate(entries):
            owner=int(entry.group(1)[4:],16)
            end=entries[i+1].start() if i+1<len(entries) else len(source)
            yield file, owner, source[entry.end():end]

def window(file, owner, body, target, before=24, after=32):
    distance=target-owner
    if distance<0 or distance%4: return None
    comments=list(COMMENT.finditer(body))
    index=distance//4
    if index>=len(comments): return None
    first=max(0,index-before); last=min(len(comments),index+after+1)
    return {
      "file":file.name,"owner":f"0x{owner:08X}","target":f"0x{target:08X}",
      "instruction_index":index,
      "instructions":[{"address":f"0x{owner+i*4:08X}",
                       "instruction":comments[i].group(1),"target":i==index}
                      for i in range(first,last)]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ppc-dir",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    wanted=0x82575250
    targets=(0x82495C60,0x8257550C)
    result={"purpose":"Verbatim native AOT source extraction; no PPC code is modified.",
            "function":None,"callsite_windows":[]}
    found=set()
    for file,owner,body in records(args.ppc_dir):
        if owner==wanted:
            result["function"]={"name":"sub_82575250","owner":f"0x{owner:08X}",
                                "file":file.name,
                                "instruction_comment_count":len(COMMENT.findall(body)),
                                "body":body}
        for target in targets:
            item=window(file,owner,body,target)
            if item is not None:
                result["callsite_windows"].append(item); found.add(target)
    if result["function"] is None:
        raise SystemExit("sub_82575250 not found in generated PPC AOT sources")
    missing=[f"0x{x:08X}" for x in targets if x not in found]
    if missing: raise SystemExit("Callsite address(es) not mapped: "+", ".join(missing))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding="utf-8")
    fn=result["function"]
    print("XOWUE_STREAM_STALL_AOT_SOURCE "+json.dumps({
      "function":fn["name"],"file":fn["file"],
      "instruction_comments":fn["instruction_comment_count"],
      "body_chars":len(fn["body"]),
      "callsites":[{"owner":x["owner"],"target":x["target"],"file":x["file"]}
                   for x in result["callsite_windows"]]}))
if __name__=="__main__": main()
