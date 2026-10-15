#!/usr/bin/env python3
"""Conservative PS3 PowerPC direct-call candidate recovery; no code/data export."""
from __future__ import annotations
import argparse,json,struct
from collections import Counter
from pathlib import Path
class PPUFormatError(ValueError):pass
def sign(v,b):return v-(1<<b) if v&(1<<(b-1)) else v
def scan_elf(blob:bytes,opd_starts:set[int]):
 d=blob
 if len(d)<64 or d[:7]!=b'\x7fELF\x02\x02\x01' or struct.unpack_from('>H',d,18)[0]!=21:
  raise PPUFormatError("expected ELF64 MSB PPU")
 phoff,shoff=struct.unpack_from('>QQ',d,32)
 phsz,phn,shsz,shn=struct.unpack_from('>HHHH',d,54)
 if phn>256 or shn>4096 or phsz<56 or shsz<64 or phoff+phsz*phn>len(d) or shoff+shsz*shn>len(d):
  raise PPUFormatError("invalid headers")
 regions=[]
 for i in range(shn):
  _,kind,flags,va,off,size,*_=struct.unpack_from('>IIQQQQIIQQ',d,shoff+i*shsz)
  if flags&4 and kind==1 and size:
   if off+size>len(d):raise PPUFormatError('truncated executable section')
   regions.append((va,va+size,off))
 if not regions:raise PPUFormatError('no executable code sections')
 def word(va):
  if va&3:return None
  for lo,hi,off in regions:
   if lo<=va and va+4<=hi:return struct.unpack_from('>I',d,off+va-lo)[0]
  return None
 def prologue(va):
  w=word(va)
  if w is None:return False
  if w>>26==62 and ((w>>21)&31)==1 and ((w>>16)&31)==1 and (w&3)==1 and sign(w&0xfffc,16)<0:
   return True
  if w==0x7c0802a6:
   for k in range(1,5):
    n=word(va+k*4)
    if n is not None and n>>26==62 and ((n>>21)&31)==1 and ((n>>16)&31)==1 and (n&3)==1 and sign(n&0xfffc,16)<0:
     return True
  return False
 calls=Counter();callers={};total=0
 for lo,hi,off in regions:
  for pc in range((lo+3)&~3,hi-3,4):
   w=word(pc)
   if w is None or w>>26!=18 or not(w&1):continue
   total+=1
   delta=sign(w&0x3fffffc,26)
   target=(delta if w&2 else pc+delta)&0xffffffffffffffff
   if word(target) is None:continue
   calls[target]+=1
   callers.setdefault(target,pc)
 candidates=[];no_prologue=0
 for addr,count in calls.items():
  if addr in opd_starts:continue
  if prologue(addr):
   candidates.append({'entry':hex(addr),'incoming_direct_calls':count,'sample_caller':hex(callers[addr])})
  else:no_prologue+=1
 candidates.sort(key=lambda x:(-x['incoming_direct_calls'],int(x['entry'],16)))
 return {'schema':'ascension-recomp/ppu-direct-call-candidates-v1',
         'executable_sections':len(regions),'direct_bl_instructions':total,
         'distinct_in_bounds_direct_targets':len(calls),
         'recovered_not_in_opd':len(candidates),
         'unknown_targets_without_strong_prologue':no_prologue,
         'candidates':candidates,
         'warning':'Only call+prologue candidates. Function boundaries are NOT validated; may include false positives. No code bytes exported.'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('elf',type=Path)
 p.add_argument('--functions',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args()
 entries={int(x['start'],0) for x in json.loads(a.functions.read_text())}
 result=scan_elf(a.elf.read_bytes(),entries)
 a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(result,indent=2)+'\n')
 print('BL scanned:',result['direct_bl_instructions'],'new candidates:',result['recovered_not_in_opd'])
