#!/usr/bin/env python3
"""M7.63 strict whole-ELF OPD+CFG semantic family expansion.
No runtime PowerPC interpretation; only offline ELF and immutable IR inputs.
Rejects unsupported opcodes, branches, ambiguous function boundaries; preserves
XER.CA, CR0 for addic., guest big-endian loads/stores and LR/CTR.
"""
import argparse, base64, gzip, hashlib, json, struct
from pathlib import Path
import m762_pipeline as base

IR_SHA=None

def decode(w):
    try:return base_decode(w)
    except ValueError:pass
    op=w>>26;d=(w>>21)&31;a=(w>>16)&31;b=(w>>11)&31
    imm=base.sx16(w&65535)
    if op in (12,13):return ['addic.' if op==13 else 'addic',d,a,imm]
    mem={32:'lwz',33:'lwzu',34:'lbz',35:'lbzu',36:'stw',37:'stwu',38:'stb',39:'stbu',40:'lhz',41:'lhzu',42:'lha',43:'lhau',44:'sth',45:'sthu'}
    if op in mem:
        update=bool(op&1)
        if update and (a==0 or (op<36 and d==a)):
            raise ValueError('invalid update base or destination alias')
        return [mem[op],d,a,imm]
    if op in (58,62):
        ds=w&3
        if op==58:
            if ds not in (0,1,2):raise ValueError('invalid LD DS selector')
            if ds==1 and (a==0 or d==a):raise ValueError('invalid LDU base alias')
            return [['ld','ldu','lwa'][ds],d,a,imm&~3]
        if ds not in (0,1):raise ValueError('invalid STD DS selector')
        if ds==1 and a==0:raise ValueError('invalid STDU base')
        return [['std','stdu'][ds],d,a,imm&~3]
    if op==31:
        xo=(w>>1)&1023
        if (w&1)==0 and xo in (10,266,40,444,28,316,60,124,104,235):
            if xo==104 and b:raise ValueError('NEG reserved RB nonzero')
            return ['xo',xo,d,a,b]
        if (w&1)==0 and xo in (339,467):
            spr=((w>>16)&31)|((w>>6)&0x3e0)
            if spr in (8,9):return ['spr',xo,d,spr]
    raise ValueError('unsupported PPC opcode family: %08X'%w)

base_decode=base.decode

def index(elf,baseline):
    orig=base.decode
    try:
        base.decode=decode
        im,calls,valid,rows,rej,bad=base.inventory(elf)
    finally:
        base.decode=orig
    old=json.loads(Path(baseline).read_text())
    known={int(x['pc'],16) for x in old['accepted']}
    fresh=[x for x in valid if x['pc'] not in known]
    if 0x002c53bc not in {x['pc'] for x in fresh}:raise ValueError('real iPhone stop not translated')
    for r in fresh:
        if not r['ir'] or r['ir'][-1]!=['blr']:raise ValueError('unsafe terminal')
    return dict(schema='ascension-m763-strict-isa-expansion-1',source_sha256=base.ELF_SHA,
                upstream_ps3recomp_sha='39a36296511c445707adabcd312f0b740cfbd694',
                discovery='entire OPD and file-backed direct calls, exclude already registered M762',
                previous_entries=len(known),candidates=len(rows),new_lifted=len(fresh),
                new_ppc_words=sum(r['count'] for r in fresh),reject_counts=dict(rej),
                accepted=fresh)

def emit_sources(rows,out,chunk=96):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);sources=[]
    for start in range(0,len(rows),chunk):
        lines=['/* M7.63 static PPC64 semantic lowering from owner-authenticated OPD/CFG. No interpreter. */',
               '#include "ppu_bridge.h"','#include <stdint.h>']
        for spec in rows[start:start+chunk]:
            pc=spec['pc'];lines.append('int ar_m763_native_%08x(ppu_context *c) {'%pc)
            for i,w in enumerate(spec['ir']):
                op=w[0]
                if op=='blr':lines.append('  c->cia=c->lr;return AR_OK;');continue
                if op in ('addi','addis','addic','addic.'):
                    d,a,imm=w[1:];sh=65536 if op=='addis' else 1
                    lines.append('  {uint64_t lhs=%s,rhs=UINT64_C(0x%016x);'%('c->gpr[%d]'%a if a or op in ('addic','addic.') else 'UINT64_C(0)',(imm*sh)&0xffffffffffffffff))
                    lines.append('   c->gpr[%d]=lhs+rhs;'%d)
                    if op in ('addic','addic.'):
                        lines.append('   c->xer=(c->xer&~UINT32_C(0x20000000)) | (c->gpr[%d]<lhs?UINT32_C(0x20000000):0U);'%d)
                    if op=='addic.':
                        lines.append('   uint32_t cr0=((int64_t)c->gpr[%d]<0?8u:((int64_t)c->gpr[%d]>0?4u:2u)) | ((c->xer>>31)&1u);'%(d,d))
                        lines.append('   c->cr=(c->cr&UINT32_C(0x0fffffff))|(cr0<<28);')
                    lines.append('  }');continue
                if op in ('ori','oris','xori','xoris'):
                    rs,ra,imm=w[1:];imm=imm*65536 if op in ('oris','xoris') else imm
                    lines.append('  c->gpr[%d]=c->gpr[%d]%sUINT64_C(0x%x);'%(ra,rs,'|' if op in ('ori','oris') else '^',imm));continue
                if op=='xo':
                    xo,d,a,b=w[1:]
                    if xo in (10,266,40):
                        lhs='c->gpr[%d]'%a;rhs='c->gpr[%d]'%b
                        if xo==40:calc=f'{rhs}-{lhs}'
                        else:calc=f'{lhs}+{rhs}'
                        if xo==10:
                            lines.append('  {uint64_t left=%s,right=%s; c->gpr[%d]=left+right;'%(lhs,rhs,d))
                            lines.append('   c->xer=(c->xer&~UINT32_C(0x20000000))|(c->gpr[%d]<left?UINT32_C(0x20000000):0U);}'%d)
                        else:lines.append('  c->gpr[%d]=%s;'%(d,calc))
                    elif xo in (444,28,316,60,124):
                        aexpr='c->gpr[%d]'%d;bexpr='c->gpr[%d]'%b
                        res={444:f'({aexpr}|{bexpr})',28:f'({aexpr}&{bexpr})',316:f'({aexpr}^{bexpr})',60:f'({aexpr}&~{bexpr})',124:f'~({aexpr}|{bexpr})'}[xo]
                        lines.append('  c->gpr[%d]=%s;'%(a,res))
                    elif xo==104:lines.append('  c->gpr[%d]=UINT64_C(0)-c->gpr[%d];'%(d,a))
                    elif xo==235:lines.append('  c->gpr[%d]=(uint64_t)(int64_t)(int32_t)(uint32_t)((uint64_t)(uint32_t)c->gpr[%d]*(uint64_t)(uint32_t)c->gpr[%d]);'%(d,a,b))
                    else:raise ValueError('unrecognized XO')
                    continue
                if op=='spr':
                    xo,rs,spr=w[1:];field='lr' if spr==8 else 'ctr'
                    if xo==339:lines.append('  c->gpr[%d]=c->%s;'%(rs,field))
                    else:lines.append('  c->%s=c->gpr[%d];'%(field,rs))
                    continue
                if op in ('lwz','lwzu','lbz','lbzu','lhz','lhzu','lha','lhau','stw','stwu','stb','stbu','sth','sthu','ld','ldu','lwa','std','stdu'):
                    reg,ra,imm=w[1:]
                    read=op.startswith(('lw','lb','lh','ld'));update=op.endswith('u')
                    bits=8 if op.startswith(('lb','stb')) else 16 if op.startswith(('lh','sth')) else 64 if op.startswith(('ld','std')) else 32
                    if op=='lwa':bits=32
                    lines.append('  {uint64_t ea=%s + UINT64_C(0x%016x);'%('c->gpr[%d]'%ra if ra else 'UINT64_C(0)',imm&0xffffffffffffffff))
                    if bits>=16:lines.append('   if(ea & UINT64_C(%d))return AR_MEM_FAULT;'%((bits//8)-1))
                    if read:
                        lines.append('   uint%d_t val=ar_read%d(ea);'%(bits,bits))
                        lines.append('   if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;')
                        if op in ('lha','lwa'):lines.append('   c->gpr[%d]=(uint64_t)(int64_t)(int%d_t)val;'%(reg,bits))
                        else:lines.append('   c->gpr[%d]=(uint64_t)val;'%reg)
                    else:
                        lines.append('   ar_write%d(ea,(uint%d_t)c->gpr[%d]);'%(bits,bits,reg))
                        lines.append('   if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;')
                    if update:lines.append('   c->gpr[%d]=ea;'%ra)
                    lines.append('  }');continue
                raise ValueError('unsupported semantic IR '+str(w))
            lines.append('}')
        fn=out/('ppu_m763_%02d.c'%(start//chunk));fn.write_text('\n'.join(lines)+'\n');sources.append(fn)
    return sources

def emit_installer(rows,out):
    lines=['/* M7.63 original ELF SHA and RAM/ELF equality before any guest AOT registration. */',
       '#include "ppu_bridge.h"','#include <CommonCrypto/CommonDigest.h>','#include <string.h>',
       'extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);']
    lines.extend('extern int ar_m763_native_%08x(ppu_context*);'%r['pc'] for r in rows)
    lines.extend(['typedef struct {uint32_t pc,count;ar_ppu_fn fn;} ar_m763_item;',
                  'static const ar_m763_item items[]={'])
    lines.extend(' {UINT32_C(0x%08x),%du,ar_m763_native_%08x},'%(r['pc'],r['count'],r['pc']) for r in rows)
    lines.extend(['};','int ar_m763_register_discovered(const uint8_t*elf,size_t len){',
      ' if(!elf||len!=8717136u)return AR_BAD_ARGS;',
      ' uint8_t digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(elf,(CC_LONG)len,digest);',
      ' static const uint8_t expected[32]={'+','.join('0x'+base.ELF_SHA[i:i+2] for i in range(0,64,2))+'};',
      ' if(memcmp(digest,expected,32))return AR_BAD_ARGS;',
      ' for(size_t k=0;k<sizeof(items)/sizeof(items[0]);k++){',
      ' const ar_m763_item*q=&items[k];uint32_t w[6]={0};',
      ' for(uint32_t i=0;i<q->count;i+=4u){',
      ' const uint32_t n=(q->count-i<4u)?q->count-i:4u;',
      ' if(ar_m712_exec_window(elf,len,q->pc+i*4u,w)!=AR_OK||w[4]<n||!(w[5]&1u))return AR_BAD_ARGS;',
      ' for(uint32_t j=0;j<n;j++){',
      ' if(ar_read32(q->pc+(i+j)*4u)!=w[j]||ar_last_error()!=AR_OK)return AR_BAD_ARGS;',
      ' } } }',
      ' for(size_t k=0;k<sizeof(items)/sizeof(items[0]);k++){',
      ' int rc=ar_register(items[k].pc,items[k].fn);',
      ' if(rc!=AR_OK&&rc!=AR_DUPLICATE)return rc; }return AR_OK;}'])
    p=Path(out)/'ppu_m763_install.c';p.write_text('\n'.join(lines)+'\n');return p

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--elf',type=Path);parser.add_argument('--baseline',type=Path)
    parser.add_argument('--snapshot',type=Path);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    if args.elf:
        if not args.baseline:raise ValueError('--baseline required for offline original ELF')
        snap=index(args.elf,args.baseline)
        (out/'m763-semantic.json').write_text(json.dumps(snap,sort_keys=True,separators=(',',':'))+'\n')
        (out/'m763-coverage.json').write_text(json.dumps({k:v for k,v in snap.items() if k!='accepted'},indent=2)+'\n')
    else:
        snap=json.loads(args.snapshot.read_text())
        if snap['schema']!='ascension-m763-strict-isa-expansion-1' or snap['source_sha256']!=base.ELF_SHA:raise ValueError('bad immutable IR metadata')
    rows=snap['accepted']
    if len(rows)!=len({r['pc'] for r in rows}):raise ValueError('duplicate function')
    for r in rows:
        if r['count']!=len(r['ir']) or r['count']>512 or r['ir'][-1]!=['blr'] or any(w==['blr'] for w in r['ir'][:-1]):raise ValueError('ambiguous function')
    files=emit_sources(rows,out);ins=emit_installer(rows,out)
    print(json.dumps({'new_functions':len(rows),'new_PPC_words':sum(r['count'] for r in rows),'chunks':len(files),'includes_guest_stop':any(r['pc']==0x002c53bc for r in rows),'compiled_arm64':'NOT_MEASURED','executed_iphone':'NOT_MEASURED'}))

if __name__=='__main__':main()