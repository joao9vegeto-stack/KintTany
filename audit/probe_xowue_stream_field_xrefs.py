#!/usr/bin/env python3
"""Find generated PPC readers/writers of the Wolverine stream object's +168 field."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

FUNC=re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{')
COMMENT=re.compile(r'(?m)^\s*//\s+(.+?)\s*$')
LOAD=re.compile(r'^(?:lwz|lwzu|ld|ldu|lbz|lbzu|lhz|lhzu|lha)\s+\w+,\s*(?:168|0x0*0*A8)\(r\d+\)$',re.I)
STORE=re.compile(r'^(?:stw|stwu|std|stdu|stb|stbu|sth|sthu|stmw|stwcx\.)\s+.+,\s*(?:168|0x0*0*A8)\(r\d+\)$',re.I)
ADDR=re.compile(r'^addi\s+(r\d+),\s*(r\d+),\s*(?:168|0x0*0*A8)$',re.I)
TARGETS=(0x82495BF8,0x82575108,0x82575250,0x82575480,
         0x82C4BE30,0x831EDA60,0x82C2A014,0x822A0160,0x822A00C0)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ppc-dir",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    functions={}
    stores=[]; loads=[]; aliases=[]
    for file in sorted(args.ppc_dir.glob("ppc_recomp.*.cpp")):
        source=file.read_text("utf-8")
        entries=list(FUNC.finditer(source))
        for ix,e in enumerate(entries):
            owner=int(e.group(1)[4:],16)
            end=entries[ix+1].start() if ix+1<len(entries) else len(source)
            body=source[e.end():end]
            comments=[m.group(1).strip() for m in COMMENT.finditer(body)]
            if owner in TARGETS:
                functions[f"0x{owner:08X}"]={"name":f"sub_{owner:08X}",
                    "file":file.name,"instruction_comment_count":len(comments),"body":body}
            for i,ins in enumerate(comments):
                rec={"owner":f"0x{owner:08X}","pc":f"0x{owner+i*4:08X}",
                     "file":file.name,"instruction":ins}
                if STORE.match(ins):
                    rec["context"]=comments[max(0,i-6):min(len(comments),i+7)]
                    rec["context_start"]=f"0x{owner+max(0,i-6)*4:08X}"
                    stores.append(rec)
                elif LOAD.match(ins):
                    rec["context"]=comments[max(0,i-5):min(len(comments),i+6)]
                    rec["context_start"]=f"0x{owner+max(0,i-5)*4:08X}"
                    loads.append(rec)
                elif ADDR.match(ins):
                    aliases.append(rec)
    missing=[f"0x{x:08X}" for x in TARGETS if f"0x{x:08X}" not in functions]
    out={
      "purpose":"AOT cross-reference of direct accesses to stream object offset +168 (decimal / 0xA8).",
      "target_functions":functions,
      "field_168":{"direct_store_count":len(stores),"direct_load_count":len(loads),
                   "address_alias_count":len(aliases),
                   "stores":stores[:500],"loads":loads[:500],"address_aliases":aliases[:500]},
      "missing_target_functions":missing,
      "caveat":"Direct displacement xrefs only; indexed/aliased stores may require follow-up dataflow analysis."
    }
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("XOWUE_STREAM_FIELD168_XREF "+json.dumps({
      "functions_found":list(functions),
      "stores":len(stores),"loads":len(loads),"address_aliases":len(aliases),
      "store_owners":sorted(set(x["owner"] for x in stores)),
      "missing":missing}))
    required=(0x82575250,0x82575480,0x82C4BE30,0x82575108)
    if any(f"0x{x:08X}" not in functions for x in required):
        raise SystemExit("Required stream/wait AOT function missing")
if __name__=="__main__": main()
