#!/usr/bin/env python3
"""Fail-closed bounded PPC64 CFG validator. Input ELF stays private."""
import argparse,json
from pathlib import Path
from ppu_cfg_lifter import PPUImage,sx
class CFGRejected(ValueError):pass
def inspect(words,start):
    if not words or len(words)>512 or start&3:raise CFGRejected('invalid function interval')
    end=start+4*len(words)
    pending=[start];visited=set();returns=0;linked_calls=0;edges=0
    while pending:
        pc=pending.pop()
        if pc in visited:continue
        if pc<start or pc>=end or pc&3:
            raise CFGRejected(f'reachable edge outside bounded function 0x{pc:x}')
        visited.add(pc)
        w=words[(pc-start)//4];op=w>>26;fall=pc+4;successors=[]
        if op==18:
            delta=sx(w&0x3fffffc,26);target=delta if w&2 else pc+delta
            if w&1:linked_calls+=1;successors.append(fall)
            else:
                if not start<=target<end:
                    raise CFGRejected(f'unverified tail branch 0x{pc:x}->0x{target:x}')
                successors.append(target)
        elif op==16:
            delta=sx(w&0xfffc,16);target=delta if w&2 else pc+delta
            bo=(w>>21)&31;unconditional=(bo&20)==20
            if w&1:linked_calls+=1;successors.append(fall)
            else:
                if not start<=target<end:
                    raise CFGRejected(f'conditional branch crosses bound 0x{pc:x}->0x{target:x}')
                successors.append(target)
                if not unconditional:successors.append(fall)
        elif op==19 and ((w>>1)&1023) in (16,528):
            bo=(w>>21)&31
            if w&1:linked_calls+=1;successors.append(fall)
            else:
                returns+=1
                if (bo&20)!=20:successors.append(fall)
        else:successors.append(fall)
        for nxt in successors:
            if nxt==end:raise CFGRejected(f'implicit fallthrough past final bound 0x{pc:x}')
            edges+=1
            if nxt not in visited:pending.append(nxt)
    if not returns:raise CFGRejected('no guest return reached')
    return {'schema':'ascension-recomp/ppu-cfg-bounds-v1','start':hex(start),
      'end_exclusive':hex(end),'words_in_range':len(words),
      'reachable_words':len(visited),'unreachable_words':len(words)-len(visited),
      'guest_return_branches':returns,'linked_calls':linked_calls,'cfg_edges':edges,
      'note':'Bounds check only. Does not prove instruction semantics or absence of code/data mixing.'}
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf',type=Path)
    ap.add_argument('--start',type=lambda x:int(x,0),required=True)
    ap.add_argument('--end',type=lambda x:int(x,0),required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();report=inspect(PPUImage(a.elf).words(a.start,a.end),a.start)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print('CFG OK:',report['reachable_words'],'reachable; returns:',report['guest_return_branches'])
