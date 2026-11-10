#!/usr/bin/env python3
"""Cross-reference the Wolverine stream-object fields and extract candidate class methods."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

FUNC=re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{')
COMMENT=re.compile(r'(?m)^\s*//\s+(.+?)\s*$')
STORE=re.compile(r'^(?:stw|stwu|std|stdu|stb|stbu|sth|sthu|stmw|stwcx\.)\s+.+,\s*(?:168|0x0*0*A8)\(r\d+\)$',re.I)
LOAD=re.compile(r'^(?:lwz|lwzu|ld|ldu|lbz|lbzu|lhz|lhzu|lha)\s+\w+,\s*(?:168|0x0*0*A8)\(r\d+\)$',re.I)
ADDR=re.compile(r'^addi\s+(r\d+),\s*(r\d+),\s*(164|168|0x0*0*A4|0x0*0*A8)$',re.I)
ALIAS_STORE=re.compile(r'^(?:stw|stwu|std|stdu|stb|stbu|sth|sthu|stwcx\.)\s+.+,\s*(\d+)\((r\d+)\)$',re.I)
TARGETS=(
  0x82495BF8,0x82575108,0x82575250,0x82575480,
  0x82C4BE30,0x831EDA60,0x822A0160,0x822A00C0,0x82C3EE78,
  0x82A2A848,0x82A323E0,0x82A32808,0x82A32A18,0x82A33EB0,
  0x82A3E4C0,0x82A40930,0x82A29B88,0x82A3D708,
  0x82A40AC8,0x82A40A00
)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ppc-dir",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    target_set=set(TARGETS)
    functions={}; stores=[]; loads=[]; aliases=[]; alias_stores=[]
    for file in sorted(args.ppc_dir.glob("ppc_recomp.*.cpp")):
        source=file.read_text("utf-8")
        entries=list(FUNC.finditer(source))
        for ix,e in enumerate(entries):
            owner=int(e.group(1)[4:],16)
            end=entries[ix+1].start() if ix+1<len(entries) else len(source)
            body=source[e.end():end]
            comments=[m.group(1).strip() for m in COMMENT.finditer(body)]
            if owner in target_set:
                functions[f"0x{owner:08X}"]={"name":f"sub_{owner:08X}","file":file.name,
                    "instruction_comment_count":len(comments),"body":body}
            for i,ins in enumerate(comments):
                rec={"owner":f"0x{owner:08X}","pc":f"0x{owner+i*4:08X}",
                     "file":file.name,"instruction":ins}
                if STORE.match(ins):
                    rec["context"]=comments[max(0,i-6):min(len(comments),i+7)]
                    rec["context_start"]=f"0x{owner+max(0,i-6)*4:08X}"
                    stores.append(rec)
                elif LOAD.match(ins):
                    rec["context"]=comments[max(0,i-5):min(len(comments),i+6)]
                    loads.append(rec)
                m=ADDR.match(ins)
                if m:
                    dest,base,disp=m.groups()
                    disp=164 if disp.lower() in ("164","0xa4") else 168
                    rec.update({"alias_register":dest,"base_register":base,"field_offset":disp})
                    aliases.append(rec)
                    # Capture stores through the computed field pointer before it is
                    # overwritten. rX = object + 164/168; a store at 0/4(rX)
                    # may be the otherwise invisible field producer.
                    for j in range(i+1,min(len(comments),i+49)):
                        sm=ALIAS_STORE.match(comments[j])
                        if sm and sm.group(2)==dest:
                            displacement=int(sm.group(1),0)
                            if (disp==164 and displacement in (0,4)) or (disp==168 and displacement==0):
                                alias_stores.append({
                                  "owner":f"0x{owner:08X}","file":file.name,
                                  "alias_pc":f"0x{owner+i*4:08X}",
                                  "store_pc":f"0x{owner+j*4:08X}",
                                  "field_base":f"object+{disp}",
                                  "effective_field":f"object+{disp+displacement}",
                                  "alias_instruction":ins,
                                  "store_instruction":comments[j],
                                  "context":comments[max(0,i-4):min(len(comments),j+5)]
                                })
    missing=[f"0x{x:08X}" for x in TARGETS if f"0x{x:08X}" not in functions]
    result={
      "purpose":"AOT cross-reference of stream cursor/completion fields and candidate reader class.",
      "target_functions":functions,
      "field_168":{"direct_store_count":len(stores),"direct_load_count":len(loads),
                   "address_aliases":aliases,"stores":stores,"loads":loads,
                   "alias_based_stores":alias_stores},
      "missing_target_functions":missing,
      "caveat":"A field offset match is not sufficient to identify the same runtime object; register/dataflow and the actual vtable still need correlation."
    }
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("XOWUE_STREAM_FIELD168_CLASS_XREF "+json.dumps({
      "functions_found":list(functions),"missing":missing,
      "direct_stores":len(stores),"direct_loads":len(loads),
      "alias_count":len(aliases),"alias_based_stores":len(alias_stores),
      "alias_store_owners":sorted(set(x["owner"] for x in alias_stores))
    }))
    required=(0x82575250,0x82575480,0x82575108,0x82C4BE30,
              0x82A2A848,0x82A32A18,0x82A33EB0,0x82A40AC8)
    absent=[f"0x{x:08X}" for x in required if f"0x{x:08X}" not in functions]
    if absent: raise SystemExit("Required stream/candidate class source missing: "+", ".join(absent))
if __name__=="__main__": main()
