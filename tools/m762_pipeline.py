#!/usr/bin/env python3
"""M7.62: deterministic PPU ELF OPD/CFG inventory and conservative AOT.
Offline: original owner ELF. CI: only owner-produced semantic IR snapshot, never game ELF.
Only proven straight-line integer subset is generated; fail closed on all others.
"""
from __future__ import annotations
import argparse, bisect, collections, gzip, hashlib, json, struct
from pathlib import Path
ELF_SHA='4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5'
PREFIX='ar_m762_native_'
def fmt(x):return '0x%08X'%x
def sx16(x):return x-65536 if x&32768 else x
class Image:
 def __init__(self,path):
  self.raw=Path(path).read_bytes();b=self.raw
  if hashlib.sha256(b).hexdigest()!=ELF_SHA:raise ValueError('wrong canonical owner ELF SHA256')
  if b[:7]!=b'\x7fELF\x02\x02\x01' or struct.unpack_from('>HH',b,16)!=(2,21):raise ValueError('not ELF64 PPC64 BE')
  self.entry=struct.unpack_from('>Q',b,24)[0]
  po,ps,pn=struct.unpack_from('>Q',b,32)[0],struct.unpack_from('>H',b,54)[0],struct.unpack_from('>H',b,56)[0]
  if ps<56 or po+ps*pn>len(b):raise ValueError('program headers invalid')
  self.segments=[]
  for i in range(pn):
   typ,fl,of,va,_,fs,ms,al=struct.unpack_from('>IIQQQQQQ',b,po+i*ps)
   if typ==1 and fs:
    if fs>ms or of+fs>len(b):raise ValueError('bad PT_LOAD')
    self.segments.append(dict(offset=of,va=va,filesz=fs,memsz=ms,flags=fl))
  self.x=[s for s in self.segments if s['flags']&1]
  so,ss,sn=struct.unpack_from('>Q',b,40)[0],struct.unpack_from('>H',b,58)[0],struct.unpack_from('>H',b,60)[0]
  if ss<64 or so+ss*sn>len(b):raise ValueError('section table invalid')
  sections=[struct.unpack_from('>IIQQQQIIQQ',b,so+i*ss) for i in range(sn)]
  descriptor=[s for s in sections if s[3]<=self.entry<s[3]+s[5] and (s[2]&2) and not(s[2]&4) and s[5]>=16]
  if len(descriptor)!=1:raise ValueError('OPD section ambiguous')
  _,_,_,va,offset,size,*_=descriptor[0]
  if offset+size>len(b) or size%8:raise ValueError('OPD truncated')
  self.opd_section=dict(vaddr=va,size=size,offset=offset)
  descriptors=[struct.unpack_from('>II',b,offset+i) for i in range(0,size,8)]
  entry_desc=self.read(self.entry,8)
  self.entry_code,self.toc=struct.unpack('>II',entry_desc)
  self.opd=sorted(set(code for code,toc in descriptors if toc==self.toc and code%4==0 and self.executable(code,4)))
  if self.entry_code not in self.opd:raise ValueError('entry not present in OPD')
  self.opd_descriptors=len(descriptors)
 def executable(self,va,n):return any(s['va']<=va and va+n<=s['va']+s['filesz'] for s in self.x)
 def read(self,va,n):
  for s in self.segments:
   if s['va']<=va and va+n<=s['va']+s['filesz']:
    return self.raw[s['offset']+va-s['va']:s['offset']+va-s['va']+n]
  raise ValueError('outside file-backed PT_LOAD %08x'%va)
 def word(self,va):return struct.unpack('>I',self.read(va,4))[0]
def direct_target(pc,w):
 li=w&0x03fffffc
 if li&0x02000000:li-=0x04000000
 return (li if w&2 else pc+li)&0xffffffff
def decode(w):
 if w==0x4e800020:return ['blr']
 op=w>>26;d=(w>>21)&31;a=(w>>16)&31;imm=w&65535
 if op in (14,15):return ['addi' if op==14 else 'addis',d,a,sx16(imm)]
 if op in (24,25,26,27):return [{24:'ori',25:'oris',26:'xori',27:'xoris'}[op],d,a,imm]
 raise ValueError('unsupported opcode=%02X word=%08X'% (op,w))
def inventory(elf):
 im=Image(elf);opd=im.opd;calls=collections.defaultdict(list)
 # OPD regions only; may contain data: call results remain heuristic until proven.
 for i,pc in enumerate(opd[:-1]):
  for at in range(pc,opd[i+1],4):
   w=im.word(at)
   if w>>26==18 and w&1:
    target=direct_target(at,w)
    if im.executable(target,4):calls[target].append(at)
 seeds=sorted(set(opd)|set(calls))
 statuses=[];accepted=[];rejections=collections.Counter();bad_ops=collections.Counter()
 for ix,pc in enumerate(seeds):
  opd_type=pc in set(opd)
  following=seeds[ix+1] if ix+1<len(seeds) else max(s['va']+s['filesz'] for s in im.x)
  # OPD entries are authoritative code pointers; CFG target is a heuristic.
  if not im.executable(pc,4):continue
  max_range=following-pc
  reason='';end=following;origin='opd' if opd_type else 'direct_call_target'
  if max_range<4 or max_range%4:reason='ambiguous_boundary'
  elif max_range>2048 and opd_type:reason='oversized_opd_interval'
  elif not opd_type:
   # Only accept CFG candidates with a provable straight-line BLR before
   # another known entry. No internal BC/BL permitted in this strict subset.
   term=None
   for at in range(pc,min(following,pc+2048),4):
    if im.word(at)==0x4e800020:
     term=at+4;break
   if term is None:reason='ambiguous_cfg_boundary'
   else:end=term
  offender_pc=None;offender_opcode=None
  if not reason:
   raw=im.read(pc,end-pc)
   words=struct.unpack('>'+str(len(raw)//4)+'I',raw)
   if words[-1]!=0x4e800020:reason='ambiguous_terminal'
   else:
    decoded=[]
    for k,w in enumerate(words):
     if w==0x4e800020 and k!=len(words)-1:
      reason='ambiguous_internal_return';offender_pc=pc+k*4;offender_opcode=w;break
     try:decoded.append(decode(w))
     except ValueError as err:
      reason='unsupported_opcode_semantics';bad_ops['%02X:%08X'%(w>>26,w)]+=1
      offender_pc=pc+k*4;offender_opcode=w
      break
    if not reason:
     spec={'pc':pc,'count':len(words),'ir':decoded,'origin':origin,
           'sha256':hashlib.sha256(raw).hexdigest()}
     accepted.append(spec)
  if reason:
   rejections[reason]+=1
   row={'pc':fmt(pc),'origin':origin,'status':'rejected','reason':reason,
        'first_word':fmt(im.word(pc)) if im.executable(pc,4) else 'not_executable'}
   if offender_pc is not None:
    row['offending_pc']=fmt(offender_pc)
    row['offending_opcode']=fmt(offender_opcode)
   statuses.append(row)
  else:statuses.append({'pc':fmt(pc),'origin':origin,'status':'lifted','count':len(decoded)})
 return im,calls,accepted,statuses,rejections,bad_ops

def emit_sources(specs,out,chunk=128):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 parts=[]
 for num in range(0,len(specs),chunk):
  part=specs[num:num+chunk];src=['/* Generated from authenticated GOWA.ELF static semantic IR; NOT a PPC interpreter. */',
                                 '#include "ppu_bridge.h"']
  for s in part:
   pc=s['pc'];src.append('int ar_m762_native_%08x(ppu_context*c) {'%pc)
   for w in s['ir']:
    op=w[0]
    if op=='blr':src.append('  c->cia=c->lr;return AR_OK;')
    elif op in ('addi','addis'):
     d,a,imm=w[1:];shift=65536 if op=='addis' else 1
     src.append('  c->gpr[%d]=%s+UINT64_C(0x%016x);'%(d,('c->gpr[%d]'%a) if a else 'UINT64_C(0)',(imm*shift)&0xffffffffffffffff))
    else:
     rs,ra,u=w[1:];u=u*65536 if op in ('oris','xoris') else u
     symbol='|' if op in ('ori','oris') else '^'
     src.append('  c->gpr[%d]=c->gpr[%d]%sUINT64_C(0x%x);'%(ra,rs,symbol,u))
   src.append('}')
  fn='runtime/ppu_m762_%02d.c'%(num//chunk)
  (out/Path(fn).name).write_text('\n'.join(src)+'\n')
  parts.append(fn)
 return parts

def emit_installer(specs,out):
 s=['/* Auto-discovered owner OPD+CFG AOT. Validate whole original ELF SHA256 and guest RAM before registration. */',
 '#include "ppu_bridge.h"','#include <CommonCrypto/CommonDigest.h>','#include <string.h>',
 'extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);']
 for q in specs:s.append('extern int ar_m762_native_%08x(ppu_context*);'%q['pc'])
 s.append('typedef struct {uint32_t pc,count;ar_ppu_fn fn;} ar_m762_item;')
 s.append('static const ar_m762_item m762_items[]={')
 for q in specs:s.append('{UINT32_C(0x%08x),%du,ar_m762_native_%08x},'%(q['pc'],q['count'],q['pc']))
 s.append('};')
 s.append('int ar_m762_register_discovered(const uint8_t *elf,size_t len) {')
 s.append(' if(!elf||len!=8717136u)return AR_BAD_ARGS;')
 s.append(' uint8_t digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(elf,(CC_LONG)len,digest);')
 s.append(' static const uint8_t expected[32]={'+','.join('0x'+ELF_SHA[i:i+2] for i in range(0,64,2))+'};')
 s.append(' if(memcmp(digest,expected,32))return AR_BAD_ARGS;')
 s.append(' for(size_t k=0;k<sizeof(m762_items)/sizeof(m762_items[0]);k++){')
 s.append('  const ar_m762_item*q=&m762_items[k];uint8_t guest[2048],original[2048];')
 s.append('  if(q->count>512u)return AR_BAD_ARGS;')
 s.append('  for(uint32_t i=0;i<q->count;i+=4u){uint32_t w[6]={0};')
 s.append('   const uint32_t n=q->count-i<4u?q->count-i:4u;')
 s.append('   if(ar_m712_exec_window(elf,len,q->pc+i*4u,w)!=AR_OK||w[4]<n||!(w[5]&1u))return AR_BAD_ARGS;')
 s.append('   for(uint32_t j=0;j<n;j++){uint32_t v=w[j];uint8_t *p=original+(i+j)*4u;')
 s.append('    p[0]=(uint8_t)(v>>24);p[1]=(uint8_t)(v>>16);p[2]=(uint8_t)(v>>8);p[3]=(uint8_t)v;}')
 s.append('  }')
 s.append('  if(ar_vm_read_bytes(q->pc,guest,q->count*4u)!=AR_OK||')
 s.append('     memcmp(original,guest,q->count*4u))return AR_BAD_ARGS;')
 s.append(' }')
 s.append(' for(size_t k=0;k<sizeof(m762_items)/sizeof(m762_items[0]);k++){')
 s.append('  const ar_m762_item*q=&m762_items[k];int rc=ar_register(q->pc,q->fn);')
 s.append('  if(rc!=AR_OK&&rc!=AR_DUPLICATE)return rc;')
 s.append(' }return AR_OK;}')
 (Path(out)/'ppu_m762_install.c').write_text('\n'.join(s)+'\n')

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--elf',type=Path)
 ap.add_argument('--snapshot',type=Path)
 ap.add_argument('--output-dir',required=True,type=Path)
 args=ap.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
 if args.elf:
  im,calls,specs,rows,rej,bad=inventory(args.elf)
  report={'schema':'ascension-m762-full-opd-cfg-inventory-1','source_sha256':ELF_SHA,
    'upstream_ps3recomp_sha':'39a36296511c445707adabcd312f0b740cfbd694',
    'source_mode':'original_ELF_offline', 'elf_entry_opd':fmt(im.entry),
    'entry_code':fmt(im.entry_code),'toc':fmt(im.toc),
    'segments':im.segments,'opd_section':im.opd_section,
    'opd_descriptors':im.opd_descriptors,'opd_unique':len(im.opd),
    'direct_call_targets':len(calls),'total_unique_candidates':len(rows),
    'fully_lifted':len(specs),'fully_lifted_words':sum(q['count'] for q in specs),
    'fully_lifted_from_opd':sum(q['origin']=='opd' for q in specs),
    'fully_lifted_from_cfg':sum(q['origin']=='direct_call_target' for q in specs),
    'reject_counts':dict(rej),'unsupported_opcode_words_top':bad.most_common(64),
    'functions':rows,'accepted':[{'pc':fmt(q['pc']),'count':q['count'],'sha256':q['sha256'],'origin':q['origin']} for q in specs],
    'native_arm64_compiled':'NOT_MEASURED','macho_linked':'NOT_MEASURED','device_executed':'NOT_MEASURED',
    'not_a_global_code_denominator':True,'host_guest_fs':'NOT_MEASURED','guest_rsx':'NOT_MEASURED'}
  (out/'m762-full-inventory.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
  snap={'schema':'ascension-m762-aot-semantic-ir-1','source_sha256':ELF_SHA,'accepted':specs}
  (out/'m762-snapshot.json').write_text(json.dumps(snap,separators=(',',':'),sort_keys=True)+'\n')
 else:
  snap=json.loads(args.snapshot.read_text());specs=snap['accepted']
  if snap.get('source_sha256')!=ELF_SHA:raise ValueError('source hash not canonical')
  if len({s['pc'] for s in specs})!=len(specs):raise ValueError('duplicate PC')
  for s in specs:
   if s['count']!=len(s['ir']) or not s['ir'] or s['ir'][-1]!=['blr'] or s['count']>512:raise ValueError('bad strict function IR')
   for index,instr in enumerate(s['ir']):
    if instr[0] not in ('addi','addis','ori','oris','xori','xoris','blr'):raise ValueError('unsafe IR opcode')
    if instr[0]=='blr' and index!=len(s['ir'])-1:raise ValueError('internal unconditional return')
    if instr[0]!='blr' and (len(instr)!=4 or not all(isinstance(v,int) for v in instr[1:])):raise ValueError('unsafe IR operands')
 parts=emit_sources(specs,out);emit_installer(specs,out)
 print(json.dumps({'lifted':len(specs),'words':sum(s['count'] for s in specs),'source_files':parts,'compiled':'NOT_MEASURED','runtime_executed':'NOT_MEASURED'}))
if __name__=='__main__':main()