#!/usr/bin/env python3
"""Independent read-only PRX import audit of private owner ELF. No game bytes serialized."""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,struct
from pathlib import Path
SHA='4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5'
SIZE=8717136
STUB=0x00669A84
B32=lambda b,o:struct.unpack_from('>I',b,o)[0]
B16=lambda b,o:struct.unpack_from('>H',b,o)[0]
B64=lambda b,o:struct.unpack_from('>Q',b,o)[0]
def analyze(data:bytes):
 assert len(data)==SIZE and hashlib.sha256(data).hexdigest()==SHA,'owner ELF SHA mismatch'
 assert data[:7]==b'\x7fELF\x02\x02\x01','ELF64 must be big-endian'
 phoff=B64(data,32);phentsize=B16(data,54);n=B16(data,56)
 assert n and phentsize>=56 and phoff+phentsize*n<=len(data)
 segments=[]; prx=None
 for i in range(n):
  at=phoff+i*phentsize;kind=B32(data,at)
  if kind==1:segments.append(dict(off=B64(data,at+8),vaddr=B64(data,at+16),size=B64(data,at+32),flags=B32(data,at+4)))
  if kind==0x60000002:assert prx is None;prx=B64(data,at+16)
 assert prx
 def at(va,size=1,execute=False):
  for s in segments:
   if (not execute or s['flags']&1) and s['vaddr']<=va and va+size<=s['vaddr']+s['size']:
    o=s['off']+va-s['vaddr'];assert o+size<=len(data)
    return o
  raise ValueError(f'guest virtual address not file-backed: {va:#x}')
 h=at(prx,32);assert B32(data,h+4)==0x1b434cec
 first,last=B32(data,h+24),B32(data,h+28)
 assert 0<last-first<=32768
 libs=[];cursor=first
 while cursor<last:
  p=at(cursor,28);step=data[p];assert 28<=step<=128 and cursor+step<=last
  libs.append(dict(nfunc=B16(data,p+6),name_va=B32(data,p+16),nid_va=B32(data,p+20),stub_va=B32(data,p+24)))
  cursor+=step
 assert cursor==last
 imports=[]
 for lib in libs:
  if not lib['nid_va'] or not lib['stub_va']:continue
  count=lib['nfunc']
  if count==0:
   next_nid=min([q['nid_va'] for q in libs if q['nid_va']>lib['nid_va']]or[0xffffffff])
   next_stub=min([q['stub_va'] for q in libs if q['stub_va']>lib['stub_va']]or[0xffffffff])
   ns=(next_nid-lib['nid_va'])//4 if next_nid!=0xffffffff and (next_nid-lib['nid_va'])%4==0 else 0
   ss=(next_stub-lib['stub_va'])//4 if next_stub!=0xffffffff and (next_stub-lib['stub_va'])%4==0 else 0
   count=min(ns,ss) if ns and ss else ns or ss
  assert count<=4096
  name=b''
  if lib['name_va']:
   pos=at(lib['name_va'],1)
   name=data[pos:pos+48].split(b'\0')[0]
  module=name.decode('ascii','strict')
  for i in range(count):
   nid=B32(data,at(lib['nid_va']+4*i,4));stub=B32(data,at(lib['stub_va']+4*i,4));
   if stub:at(stub,4,execute=True)
   imports.append(dict(library=module,nid=f'0x{nid:08x}',stub=f'0x{stub:08x}'))
 target=[i for i in imports if int(i['stub'],16)==STUB]
 assert len(target)==1,(target,len(imports))
 assert target[0]['library']=='sysPrxForUser' and target[0]['nid']=='0x2f85c0ef'
 slot=0x00828298; slot_va=B32(data,at(slot,4));assert slot_va==STUB
 assert B32(data,at(STUB,4,execute=True))==0x39800000
 return {'schema':'ascension-m767-private-prx-readonly-audit-1','sha256':SHA,'imports_total':len(imports),'libraries':len({i['library'] for i in imports}),
 'stub':f'0x{STUB:08X}','library':target[0]['library'],'nid':target[0]['nid'],'source':'original ELF PRX parameter import tables',
 'raw_elf_slot_va':f'0x{slot:08X}','raw_elf_slot_value':f'0x{slot_va:08X}',
 'raw_stub_opcode':'0x39800000','HLE_binding_existing':'ar_sys_lwmutex_create',
 'live_guest_slot_value':'NOT_MEASURED','live_HLE_result':'NOT_MEASURED',
 'note':'raw ELF self-pointer is unbound descriptor, cannot assume live guest RAM slot unchanged'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('elf');ap.add_argument('--output');args=ap.parse_args()
 result=analyze(Path(args.elf).read_bytes());js=json.dumps(result,indent=2,ensure_ascii=False)+'\n';print(js,end='')
 if args.output:Path(args.output).write_text(js)
