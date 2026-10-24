#!/usr/bin/env python3
"""Evidence-only native AOT bctrl source audit. Never interprets guest PPC."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

FUNC=re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{')
COMMENT=re.compile(r'(?m)^\s*//\s+(.+?)\s*$')
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ppc-dir',type=Path,required=True)
    ap.add_argument('--target',type=lambda x:int(x,0),default=0x82361BF4)
    ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args()
    result={'target':f'{args.target:08X}','verified_candidates':[],'nearest_predecessors':[]}
    files=sorted(args.ppc_dir.glob('ppc_recomp.*.cpp'))
    for file in files:
        source=file.read_text('utf-8')
        functions=list(FUNC.finditer(source))
        for i,entry in enumerate(functions):
            owner=int(entry.group(1)[4:],16)
            if owner>args.target: continue
            next_pos=functions[i+1].start() if i+1<len(functions) else len(source)
            body=source[entry.end():next_pos]
            guest_comments=list(COMMENT.finditer(body))
            distance=args.target-owner
            if distance>=0 and not distance%4 and distance//4<len(guest_comments):
                instruction=guest_comments[distance//4].group(1)
                if not any(x in instruction.lower() for x in ('bctrl','bctr','bcctr')):
                    continue
                n=distance//4
                start=max(0,n-20);end=min(len(guest_comments),n+9)
                window=body[guest_comments[start].start():guest_comments[end].start() if end<len(guest_comments) else len(body)]
                result['verified_candidates'].append({
                    'owner':f'{owner:08X}','file':file.name,
                    'comment_index':n,'opcode_comment':instruction,
                    'native_context':window[:12000]})
            if distance>=0:
                result['nearest_predecessors'].append((distance,file.name,f'{owner:08X}'))
    result['nearest_predecessors']=sorted(result['nearest_predecessors'])[:8]
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('XOWUE_BCTRL_NATIVE_AOT_SOURCE '+json.dumps({
      'target':result['target'],'matching_sites':len(result['verified_candidates']),
      'nearby_owners':result['nearest_predecessors']
    }))
    for candidate in result['verified_candidates']:
        print('XOWUE_BCTRL_SOURCE owner='+candidate['owner']+' file='+candidate['file'])
        print(candidate['native_context'][:3800])
if __name__=='__main__':
    main()
