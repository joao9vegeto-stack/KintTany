#!/usr/bin/env python3
"""Find every generated PPC reference to the startup async streaming manager global."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path

FUNC=re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{')
COMMENT=re.compile(r'(?m)^\s*//\s+(.+?)\s*$')
LIS=re.compile(r'^lis\s+(r\d+),\s*-31906$',re.I)
GLOBAL_ACCESS=re.compile(r'^(lwz|stw|addi)\s+(r\d+),\s*(76|0x4C)\((r\d+)\)$',re.I)
TARGETS={
  0x82575250,0x82575108,0x82575480,0x82495BF8,0x831EDA60,
  0x82985EA0,0x8236C658,0x82380D60,0x831EE998,0x831EF9E8,
  0x8240C7D0,0x8249A428,0x824A7CD0,0x824B4B60,
  0x82573620,0x82573AE8,0x8258A8B8,0x8258A980,
  0x82693360,0x82694788,0x82694820
}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ppc-dir",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    refs=[]; target_bodies={}; direct_address_mentions=[]
    for file in sorted(args.ppc_dir.glob("ppc_recomp.*.cpp")):
        src=file.read_text("utf-8")
        entries=list(FUNC.finditer(src))
        for ix,e in enumerate(entries):
            owner=int(e.group(1)[4:],16)
            end=entries[ix+1].start() if ix+1<len(entries) else len(src)
            body=src[e.end():end]
            comments=[m.group(1).strip() for m in COMMENT.finditer(body)]
            if owner in TARGETS:
                target_bodies[f"0x{owner:08X}"]={"file":file.name,"body":body}
            for i,ins in enumerate(comments):
                m=LIS.match(ins)
                if not m: continue
                base_reg=m.group(1)
                found=[]
                for j in range(i+1,min(len(comments),i+20)):
                    a=GLOBAL_ACCESS.match(comments[j])
                    if a and a.group(4)==base_reg:
                        found.append({"pc":f"0x{owner+j*4:08X}","instruction":comments[j]})
                if found:
                    first=max(0,i-4); last=min(len(comments),i+len(found)+10)
                    refs.append({"owner":f"0x{owner:08X}","file":file.name,
                      "lis_pc":f"0x{owner+i*4:08X}","base_register":base_reg,
                      "absolute_global":"0x835E004C","accesses":found,
                      "window_start":f"0x{owner+first*4:08X}",
                      "context":comments[first:last]})
            if "0x835E004C" in body or "0x835e004c" in body:
                direct_address_mentions.append({"owner":f"0x{owner:08X}","file":file.name})
    out={
      "purpose":"Cross-reference all PPC code reading/writing the game's async stream manager pointer at 0x835E004C.",
      "references":refs,
      "direct_address_mentions":direct_address_mentions,
      "target_bodies":target_bodies,
      "interpretation_notes":[
        "A lis rX,-31906 forms 0x835E0000; a following 76(rX) access addresses 0x835E004C.",
        "Function references identify the class-manager initialization/use paths; they do not by themselves prove callback delivery.",
        "The 0x835D0794 handle/event manager is separate and is not conflated with 0x835E004C."
      ]
    }
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(out,indent=2),encoding="utf-8")
    owners=sorted(set(x["owner"] for x in refs))
    print("XOWUE_ASYNC_STREAM_MANAGER_XREF "+json.dumps({
      "reference_sites":len(refs),"function_count":len(owners),
      "owners":owners,"direct_mentions":len(direct_address_mentions),
      "target_bodies":list(target_bodies)}))
    if not refs: raise SystemExit("No references to async streaming manager global found")
if __name__=="__main__": main()
