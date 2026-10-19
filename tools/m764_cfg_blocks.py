#!/usr/bin/env python3
"""M7.64: deterministic GOWA ELF OPD/CFG direct-tail AOT, fail closed."""
import argparse,collections,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import m762_pipeline as base
SCHEMA='ascension-m764-opd-basic-block-aot-1'
MAX_WORDS=16

def decode(pc,w):
 if w>>26==18 and not w&1:return ['b',base.direct_target(pc,w)]
 if w>>26==30 and not w&1 and ((w>>2)&7)==0:
  sh=((w>>11)&31)|((w&2)<<4);mb=((w>>6)&31)|(w&32)
  if sh==0:return ['clrldi',(w>>16)&31,(w>>21)&31,mb]
 v=base.decode(w)
 if v[0] not in ('addi','addis','ori','oris','xori','xoris'):raise ValueError('opcode semantics missing')
 return v

def discover(elf):
 im=base.Image(elf)
 queue=collections.deque((pc,'opd') for pc in im.opd)
 visited=set();accepted=[];rejected=collections.Counter()
 while queue:
  pc,origin=queue.popleft()
  if pc in visited:continue
  visited.add(pc)
  if not im.executable(pc,4):rejected['non_exec']+=1;continue
  ins=[];reason='no_proven_terminal'
  for off in range(0,MAX_WORDS*4,4):
   at=pc+off
   if not im.executable(at,4):reason='crosses_code_boundary';break
   try: op=decode(at,im.word(at))
   except ValueError:reason='unsupported_instruction';break
   ins.append(op)
   if op[0]=='b':
    if not im.executable(op[1],4):reason='non_executable_branch';break
    accepted.append({'pc':pc,'origin':origin,'ir':ins,
                     'count':len(ins),'sha256':hashlib.sha256(im.read(pc,len(ins)*4)).hexdigest()})
    if op[1] not in visited:queue.append((op[1],'direct_tail'))
    reason=None;break
  if reason:rejected[reason]+=1
 return dict(schema=SCHEMA,source_sha256=base.ELF_SHA,
             entry_opd=base.fmt(im.entry),entry_code=base.fmt(im.entry_code),
             opcandidates=len(visited),opd_unique=len(im.opd),
             compiled_arm64='NOT_MEASURED',linked_macho='NOT_MEASURED',
             device_executed='NOT_MEASURED',spu='NOT_SCANNED',
             rejection_counts=dict(rejected),
             accepted=sorted(accepted,key=lambda q:q['pc']))

def validate(s):
 if s.get('schema')!=SCHEMA or s.get('source_sha256')!=base.ELF_SHA:raise ValueError('bad snapshot provenance')
 seen=set()
 for q in s['accepted']:
  pc=q['pc'];ins=q['ir']
  if not isinstance(pc,int) or pc%4 or pc in seen:raise ValueError('invalid/duplicate PC')
  seen.add(pc)
  if not ins or len(ins)>MAX_WORDS or len(ins)!=q['count']:raise ValueError('bad block size')
  if len(q.get('sha256',''))!=64 or any(ch not in '0123456789abcdef' for ch in q['sha256']):raise ValueError('bad hash')
  for i,x in enumerate(ins):
   op=x[0]
   if op=='b':
    if i!=len(ins)-1 or len(x)!=2 or not isinstance(x[1],int) or x[1]%4 or not 0<=x[1]<2**32:raise ValueError('bad tail')
   elif op in ('addi','addis','ori','oris','xori','xoris','clrldi'):
    if len(x)!=4 or any(not isinstance(v,int) for v in x[1:]) or not 0<=x[1]<=31 or not 0<=x[2]<=31:raise ValueError('bad ALU')
    if op=='clrldi' and not 0<=x[3]<=63:raise ValueError('bad mask')
    if op in ('addi','addis') and not -32768<=x[3]<=32767:raise ValueError('bad signed imm')
    if op in ('ori','oris','xori','xoris') and not 0<=x[3]<=65535:raise ValueError('bad unsigned imm')
   else:raise ValueError('untranslated instruction')
  if ins[-1][0]!='b':raise ValueError('no terminal B')
 return s

def generate(s,out):
 s=validate(s);out=Path(out);out.mkdir(parents=True,exist_ok=True)
 items=s['accepted']
 for start in range(0,len(items),128):
  lines=['/* Offline static PPC semantics, native C only. */','#include "ppu_bridge.h"','#include <stdint.h>']
  for q in items[start:start+128]:
   lines.append('int ar_m764_native_%08x(ppu_context*c){'%q['pc'])
   for x in q['ir']:
    op=x[0]
    if op=='b':lines.append(' c->cia=UINT64_C(0x%08x);return AR_TAIL;'%x[1]);continue
    d,a,v=x[1:]
    if op in ('addi','addis'):
     imm=(v*(65536 if op=='addis' else 1))&0xffffffffffffffff
     lhs='c->gpr[%d]'%a if a else 'UINT64_C(0)'
     lines.append(' c->gpr[%d]=%s+UINT64_C(0x%016x);'%(d,lhs,imm))
    elif op=='clrldi':
     mask=(1<<(64-v))-1 if v<64 else 0
     lines.append(' c->gpr[%d]=c->gpr[%d]&UINT64_C(0x%016x);'%(d,a,mask))
    else:
     imm=v*(65536 if op.endswith('is') else 1)
     lines.append(' c->gpr[%d]=c->gpr[%d]%sUINT64_C(0x%x);'%(a,d,'|' if op.startswith('or') else '^',imm))
   lines.append('}')
  (out/('ppu_m764_%02d.c'%(start//128))).write_text('\n'.join(lines)+'\n')
 lines=['/* Full canonical SHA + each live guest block SHA before registration. */',
        '#include "ppu_bridge.h"','#include <CommonCrypto/CommonDigest.h>',
        '#include <stdint.h>','#include <string.h>']
 lines.extend('extern int ar_m764_native_%08x(ppu_context*);'%q['pc'] for q in items)
 lines.extend(['typedef struct {uint32_t pc,count;uint8_t hash[32];ar_ppu_fn fn;} entry;',
               'static const entry entries[]={'])
 for q in items:
  digest=','.join('0x'+q['sha256'][i:i+2] for i in range(0,64,2))
  lines.append(' {0x%08xu,%du,{%s},ar_m764_native_%08x},'%(q['pc'],q['count'],digest,q['pc']))
 canonical=','.join('0x'+base.ELF_SHA[i:i+2] for i in range(0,64,2))
 lines.extend(['};','int ar_m764_register_discovered(const uint8_t*elf,size_t len){',
    ' if(!elf||len!=8717136u)return AR_BAD_ARGS;',
    ' uint8_t digest[32];CC_SHA256(elf,(CC_LONG)len,digest);',
    ' static const uint8_t canonical[32]={'+canonical+'};',
    ' if(memcmp(digest,canonical,32))return AR_BAD_ARGS;',
    ' for(size_t i=0;i<sizeof(entries)/sizeof(entries[0]);i++){',
    '  uint8_t bytes[64],hash[32];const entry*e=&entries[i];',
    '  if(ar_vm_read_bytes(e->pc,bytes,e->count*4u)!=AR_OK)return AR_MEM_FAULT;',
    '  CC_SHA256(bytes,(CC_LONG)(e->count*4u),hash);',
    '  if(memcmp(hash,e->hash,32))return AR_BAD_ARGS;',
    ' }',
    ' for(size_t i=0;i<sizeof(entries)/sizeof(entries[0]);i++){',
    '  int rc=ar_register(entries[i].pc,entries[i].fn);',
    '  if(rc!=AR_OK&&rc!=AR_DUPLICATE)return rc;',
    ' }return AR_OK;',
    '}'])
 (out/'ppu_m764_install.c').write_text('\n'.join(lines)+'\n')

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--elf',type=Path);ap.add_argument('--snapshot',type=Path)
 ap.add_argument('--output-dir',type=Path,required=True)
 ap.add_argument('--write-snapshot',type=Path)
 a=ap.parse_args()
 if bool(a.elf)==bool(a.snapshot):ap.error('must specify exactly one input')
 s=discover(a.elf) if a.elf else json.loads(a.snapshot.read_text())
 validate(s)
 if a.write_snapshot:a.write_snapshot.write_text(json.dumps(s,sort_keys=True,separators=(',',':'))+'\n')
 generate(s,a.output_dir)
 print(json.dumps({'accepted':len(s['accepted']),'opd_unique':s['opd_unique'],
 'includes_00539378':any(q['pc']==0x539378 for q in s['accepted']),
 'native_link':'NOT_MEASURED','iphone_execution':'NOT_MEASURED'}))
if __name__=='__main__':main()
