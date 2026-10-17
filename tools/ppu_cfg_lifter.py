#!/usr/bin/env python3
"""Strict experimental PowerPC64 CFG -> C AOT. No game code in this repository.

Rejects unknown instructions and unsafe function ranges. Direct branches use
function-local labels, remote branches return a tail-dispatch status, and
linked calls use a host callback. NOT a full PPU/SPU/RSX implementation.
"""
from __future__ import annotations
import argparse
import json
import struct
from collections import Counter
from pathlib import Path

class Unsupported(ValueError): pass

PROLOGUE = r'''#include <stdint.h>
#include "ppu_context.h"
typedef ppu_context ppu_ctx;
typedef uint64_t u64;
typedef uint32_t u32;
typedef int32_t s32;
extern u64 ar_read64(u64);
extern u32 ar_read32(u64);
extern uint16_t ar_read16(u64);
extern uint8_t ar_read8(u64);
extern void ar_write64(u64,u64);
extern void ar_write32(u64,u32);
extern void ar_write16(u64,uint16_t);
extern void ar_write8(u64,uint8_t);
extern int ar_guest_call(ppu_ctx*, u64);
extern int ar_guest_syscall(ppu_ctx*);
/* 0: return to guest LR; 1: tail dispatch; negative: host failure */
static inline u32 ar_rotl32(u32 v, unsigned sh) {
    sh &= 31U; return sh ? (u32)((v<<sh) | (v>>(32U-sh))) : v;
}
static inline u64 ar_rotl64(u64 v, unsigned sh) {
    sh &= 63U; return sh ? ((v<<sh) | (v>>(64U-sh))) : v;
}
static inline u64 ar_data32(u32 v) {
    return ((u64)v << 32) | (u64)v;
}
'''

def sx(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value

def mask32(mb: int, me: int) -> int:
    mask = 0
    pos = mb
    for _ in range(32):
        mask |= 1 << (31-pos)
        if pos == me: break
        pos = (pos+1) % 32
    return mask

def mask64(mb: int, me: int) -> int:
    mask = 0
    pos = mb
    for _ in range(64):
        mask |= 1 << (63 - pos)
        if pos == me: break
        pos = (pos + 1) % 64
    return mask

def lift(words: list[int] | tuple[int, ...], base: int, name: str = 'ppu_sample') -> tuple[str,dict]:
    if not words or len(words)>512 or base & 3:
        raise Unsupported('invalid function length / address')
    needs_fp=any(((w>>26) in (48,50,52,54)) or
                 ((w>>26)==63 and ((w>>1)&1023) in (18,846))
                 for w in words)
    needs_vmx=any(((w>>26)==4 and (w&2047) in (652,780,844,908)) or
                  ((w>>26)==31 and ((w>>1)&1023) in
                   (103,359,519,775,551,807,231,487,647,903,679,935))
                  for w in words)
    lines=[PROLOGUE, '#include "ppu_vmx_cell.h"' if needs_vmx else '',
           '#include "ppu_fp_scalar.h"' if needs_fp else '',
           f'int {name}(ppu_ctx *c) {{']
    hist=Counter()
    addresses={base+4*i for i in range(len(words))}
    def e(stmt: str):lines.append('    '+stmt)
    def reg(i: int):return f'c->gpr[{i}]'
    def addr_base(i: int):return reg(i) if i else '0ULL'
    def record(expression: str, field: int=0):
        offset=(7-field)*4
        e(f'c->cr=(c->cr & ~(15U << {offset})) | (u32)((({expression}) | ((c->xer >> 31)&1U)) << {offset});')
    def cmp_expr(lhs:str,rhs:str):
        return f'(({lhs} < {rhs}) ? 8U : (({lhs} > {rhs}) ? 4U : 2U))'
    def terminate_to(target: int | str, lk:bool, pc:int):
        if lk:e(f'c->lr=0x{pc+4:x}ULL;')
        if isinstance(target,int) and target in addresses:
            e(f'goto L_{target:x};')
        else:
            val = f'0x{target:x}ULL' if isinstance(target,int) else target
            if lk:e(f'if(ar_guest_call(c,{val})) return -3;')
            else:e(f'c->cia={val}; return 1;')
    for i,w in enumerate(words):
        pc=base+4*i
        op=(w>>26)&63
        d=(w>>21)&31; a=(w>>16)&31; b=(w>>11)&31
        imm=sx(w&0xffff,16)
        e(f'L_{pc:x}: ;')
        def branch_test(bo:int, bi:int, ctr_is_target=False):
            parts=[]
            if not (bo & 4):
                if ctr_is_target:raise Unsupported('bcctr cannot decrement CTR')
                e('c->ctr = c->ctr - 1ULL;')
                parts.append('(c->ctr == 0ULL)' if bo & 2 else '(c->ctr != 0ULL)')
            if not (bo & 16):
                parts.append(f'(((c->cr >> {31-bi}) & 1U) == {1 if bo&8 else 0}U)')
            return ' && '.join(parts) if parts else '1'
        if op in (48,50,52,54):
            single=1 if op in (48,52) else 0
            ea=f'({addr_base(a)}+(u64)((int64_t){imm}))'
            name='load' if op in (48,50) else 'store'
            e(f'int fpr_rc_{i}=ar_fp_{name}(c,{d},{ea},{single});')
            e(f'if(fpr_rc_{i}!=0) return fpr_rc_{i};')
            hist['fp_'+name]+=1
            continue
        if op==63:
            xo=(w>>1)&1023
            if w&1:raise Unsupported('FP Rc updates CR1 not supported yet')
            if xo==846 and a==0:
                e(f'if(ar_fp_fcfid(c,{d},{b})!=0) return -12;')
                hist['fcfid']+=1
                continue
            if xo==18:
                e(f'if(ar_fp_fdiv(c,{d},{a},{b})!=0) return -12;')
                hist['fdiv']+=1
                continue
            raise Unsupported(f'unsupported floating opcode63/{xo}')
        if op==4:
            xo=w&2047
            if xo in (780,844,908):
                if b:raise Unsupported('VMX immediate reserved bits nonzero')
                width={780:1,844:2,908:4}[xo]
                e(f'ar_vmx_splat_imm(c,{d},{a},{width});')
                hist[{780:'vspltisb',844:'vspltish',908:'vspltisw'}[xo]]+=1
                continue
            if xo==652:
                if a>3:raise Unsupported('VSPLTW index must be 0..3')
                e(f'if(ar_vmx_splatw(c,{d},{b},{a})!=0) return -12;')
                hist['vspltw']+=1
                continue
            raise Unsupported(f'unsupported vector opcode4/{xo}')
        if op==16:
            bo=(w>>21)&31; bi=(w>>16)&31
            target=(sx(w&0xfffc,16) if w&2 else pc+sx(w&0xfffc,16))
            lk=bool(w&1)
            cond=branch_test(bo,bi)
            hist['bc']+=1
            if lk:e(f'c->lr=0x{pc+4:x}ULL;')
            e(f'if ({cond}) {{')
            # LR was set even when not taken; do not reset it in the branch.
            if lk and target in addresses:
                e(f'goto L_{target:x};')
            elif lk:
                e(f'if(ar_guest_call(c,0x{target:x}ULL)) return -3;')
            else:
                terminate_to(target,False,pc)
            e('}')
            continue
        if op==18:
            target=(sx(w&0x3fffffc,26) if w&2 else pc+sx(w&0x3fffffc,26))
            terminate_to(target,bool(w&1),pc)
            hist['b/bl']+=1
            continue
        if op==19:
            xo=(w>>1)&1023; bo=(w>>21)&31;bi=(w>>16)&31;lk=bool(w&1)
            if xo==150:
                if w!=0x4c00012c:raise Unsupported('ISYNC reserved or invalid form')
                e('__atomic_thread_fence(__ATOMIC_SEQ_CST);')
                hist['isync']+=1
                continue
            if xo in (16,528):
                cond=branch_test(bo,bi,ctr_is_target=(xo==528))
                oldtarget='c->lr' if xo==16 else 'c->ctr'
                e(f'u64 target_{i}={oldtarget};')
                if lk:e(f'c->lr=0x{pc+4:x}ULL;')
                e(f'if({cond}) {{')
                if lk:e(f'if(ar_guest_call(c,target_{i})) return -3;')
                elif xo==16:
                    # Every taken BCLR without LK returns to guest LR, even
                    # when the BO/BI condition is not unconditional.
                    e(f'c->cia=target_{i}; return 0;')
                else:e(f'c->cia=target_{i}; return 1;')
                e('}')
                hist['bclr' if xo==16 else 'bcctr']+=1
                continue
            raise Unsupported(f'unsupported opcode19/{xo}')
        if op==17:
            if w!=0x44000002:raise Unsupported("unsupported syscall encoding")
            e("if(ar_guest_syscall(c)) return -9;")
            hist['sc']+=1
            continue
        if op in (10,11):
            bf=(w>>23)&7;wide=bool((w>>21)&1)
            if op==11:
                lhs=f'(int64_t){reg(a)}' if wide else f'(s32)(u32){reg(a)}'
                rhs=f'(int64_t){imm}'
            else:
                lhs=f'(u64){reg(a)}' if wide else f'(u32){reg(a)}'
                rhs=f'(u64){w&0xffff}' if wide else f'(u32){w&0xffff}'
            record(cmp_expr(lhs,rhs),bf)
            hist['cmpi']+=1
        elif op in (12,13):
            e(f'u64 old_{i}={reg(a)};')
            e(f'{reg(d)}=old_{i} + (u64)((int64_t){imm});')
            e(f'c->xer=(c->xer & ~0x20000000U) | (({reg(d)} < old_{i}) ? 0x20000000U : 0U);')
            if op==13:record(cmp_expr(f'(int64_t){reg(d)}','0LL'))
            hist['addic']+=1
        elif op in (14,15):
            v=imm << (16 if op==15 else 0)
            e(f'{reg(d)} = {addr_base(a)} + (u64)((int64_t){v});')
            hist['addi/addis']+=1
        elif op in (24,25,26,27):
            v=(w&65535) << (16 if op in (25,27) else 0)
            e(f'{reg(a)} = {reg(d)} {"|" if op in (24,25) else "^"} 0x{v:x}ULL;')
            hist['ori/xori']+=1
        elif op in (28,29):
            v=(w&65535) << (16 if op==29 else 0)
            e(f'{reg(a)} = {reg(d)} & 0x{v:x}ULL;')
            record(cmp_expr(f'(s32)(u32){reg(a)}','0'))
            hist['andi.']+=1
        elif op in (20,21,23):
            # M7.22: PPC64 M-form masked word rotations, including RLWIMI.
            # The Power ISA MASK32 wraps across the word boundary on 64-bit
            # machines: MB>ME includes the upper 32 bits as well, while
            # DATA32 duplicates the rotated word into the full 64-bit value.
            # RLWIMI must keep every bit OUTSIDE the mask from old RA.
            sh=(w>>11)&31; mb=(w>>6)&31; me=(w>>1)&31
            mask=mask32(mb,me) | (0xffffffff00000000 if mb>me else 0)
            shift=f'((u32){reg(b)} & 31U)' if op==23 else str(sh)
            e(f'u32 rot32_{i}=ar_rotl32((u32){reg(d)},{shift});')
            e(f'u64 data64_{i}=ar_data32(rot32_{i});')
            if op==20:
                e(f'{reg(a)}=({reg(a)} & ~0x{mask:016x}ULL) | (data64_{i} & 0x{mask:016x}ULL);')
                hist['rlwimi']+=1
            else:
                e(f'{reg(a)}=data64_{i} & 0x{mask:016x}ULL;')
                hist['rlwnm' if op==23 else 'rlwinm']+=1
            if w&1:record(cmp_expr(f'(int64_t){reg(a)}','0LL'))
        elif op==30:
            xo=(w>>2)&7
            if xo not in (0,1,2,3):raise Unsupported(f'unsupported MD64 rotate form {xo}')
            shift=((w>>11)&31) | ((w&2)<<4)
            mask_at=((w>>6)&31) | (w&32)
            if xo==0:mask=mask64(mask_at,63)
            elif xo==1:mask=mask64(0,mask_at)
            else:mask=mask64(mask_at,63-shift)
            e(f'u64 rot_{i}=ar_rotl64({reg(d)}, {shift});')
            if xo==3:
                e(f'{reg(a)}=({reg(a)} & ~0x{mask:016x}ULL) | (rot_{i} & 0x{mask:016x}ULL);')
            else:e(f'{reg(a)}=rot_{i} & 0x{mask:016x}ULL;')
            if w&1:record(cmp_expr(f'(int64_t){reg(a)}','0LL'))
            hist['md_rotate']+=1
        elif op in (32,34,40,58):
            fn={32:'ar_read32',34:'ar_read8',40:'ar_read16',58:'ar_read64'}[op]
            if op==58:
                if w&3:raise Unsupported('unsupported LD update/invalid form')
                imm=sx(w&0xfffc,16)
            e(f'{reg(d)}=(u64){fn}({addr_base(a)}+(u64)((int64_t){imm}));')
            hist['load']+=1
        elif op in (36,38,44,62,37):
            width={36:32,38:8,44:16,62:64,37:32}[op]
            if op==62:
                if w&3 not in (0,1):raise Unsupported('unsupported STD DS form')
                imm=sx(w&0xfffc,16)
            update=op==37 or (op==62 and (w&3)==1)
            if update and a==0:raise Unsupported('store-update with base zero')
            e(f'u64 ea_{i}={addr_base(a)}+(u64)((int64_t){imm});')
            e(f'ar_write{width}(ea_{i}, {reg(d)});')
            if update:e(f'{reg(a)}=ea_{i};')
            hist['store']+=1
        elif op==31:
            xo=(w>>1)&1023;rc=w&1
            if xo==144:
                fxm=(w>>12)&255
                l=(w>>20)&1
                if (w&0x801) or (l and (fxm==0 or fxm&(fxm-1))):
                    raise Unsupported('invalid mtcrf/mtocrf FXM, L, reserved or Rc')
                mask=sum((0xf0000000>>(4*field))
                         for field in range(8) if fxm&(0x80>>field))
                e(f'c->cr=(c->cr & ~0x{mask:08x}U) | ((u32){reg(d)} & 0x{mask:08x}U);')
                hist['mtocrf' if l else 'mtcrf']+=1
            elif xo==19:
                if w!=(0x7c000026 | (d<<21)):
                    raise Unsupported('invalid MFCR/MFOCRF/reserved encoding')
                e(f'{reg(d)}=(u64)c->cr;')
                hist['mfcr']+=1
            elif xo in (103,359,519,775,551,807,231,487,647,903,679,935):
                if w&1:raise Unsupported('VMX indexed reserved bit set')
                kind={103:0,359:0,519:1,775:1,551:2,807:2,
                      231:0,487:0,647:1,903:1,679:2,935:2}[xo]
                ea=f'({addr_base(a)}+{reg(b)})'
                name=('load' if xo in (103,359,519,775,551,807) else 'store')
                e(f'if(ar_vmx_guest_{name}(c,{d},{ea},{kind})!=0) return -2;')
                hist['vmx_'+name]+=1
            elif xo in (854,598):
                # PPC64 EIEIO/SYNC/LWSYNC: guest ordering, never a bare NOP.
                # A host-wide C11/GCC fence is stronger, safe on ARM64,
                # and remains visible in both native AOT and interpreted paths.
                allowed = (0x7c0006ac,) if xo==854 else (0x7c0004ac,0x7c2004ac)
                if w not in allowed:
                    raise Unsupported('memory barrier reserved or privileged form')
                e('__atomic_thread_fence(__ATOMIC_SEQ_CST);')
                hist['eieio' if xo==854 else
                     ('sync' if w==0x7c0004ac else 'lwsync')]+=1
            elif xo in (0,32):
                bf=(w>>23)&7;wide=bool((w>>21)&1)
                if xo==0:
                    lhs=f'(int64_t){reg(a)}' if wide else f'(s32)(u32){reg(a)}'
                    rhs=f'(int64_t){reg(b)}' if wide else f'(s32)(u32){reg(b)}'
                else:
                    lhs=f'(u64){reg(a)}' if wide else f'(u32){reg(a)}'
                    rhs=f'(u64){reg(b)}' if wide else f'(u32){reg(b)}'
                record(cmp_expr(lhs,rhs),bf);hist['cmp']+=1
            elif xo==824:
                # SRAWI: signed 32-bit arithmetic shift plus sticky SO in CR0.
                sh=b
                e(f'u32 sraw_word_{i}=(u32){reg(d)};')
                e(f'u32 sraw_result_{i}=sraw_word_{i} >> {sh}U;')
                if sh:
                    e(f'if(sraw_word_{i} & 0x80000000U) sraw_result_{i} |= UINT32_MAX << {32-sh}U;')
                e(f'u32 sraw_ca_{i}=((sraw_word_{i} & 0x80000000U) && '
                  f'((sraw_word_{i} & 0x{(1<<sh)-1:08x}U)!=0U)) ? 0x20000000U : 0U;')
                e(f'c->xer=(c->xer & ~0x20000000U) | sraw_ca_{i};')
                e(f'{reg(a)}=(u64)(int64_t)(s32)sraw_result_{i};')
                if rc:record(cmp_expr(f'(int64_t){reg(a)}','0LL'))
                hist['srawi']+=1
            elif xo in (104, 616):
                # NEG/NEGO: RT <- (0 - RA) mod 2^64. No signed C overflow.
                # The five RB/reserved bits must be zero for this X-form.
                if b: raise Unsupported('NEG reserved RB bits are nonzero')
                e(f'u64 neg_src_{i}={reg(a)};')
                e(f'{reg(d)}=0ULL-neg_src_{i};')
                if xo==616:
                    # OE=1: XER.OV is recomputed, while XER.SO stays sticky.
                    # Negating INT64_MIN overflows in signed 64-bit arithmetic.
                    e(f'u32 neg_ov_{i}=(neg_src_{i}==0x8000000000000000ULL) ? 0x40000000U : 0U;')
                    e(f'c->xer=(c->xer & ~0x40000000U) | neg_ov_{i};')
                    e(f'if(neg_ov_{i}) c->xer |= 0x80000000U;')
                if rc:record(cmp_expr(f'(int64_t){reg(d)}','0LL'))
                hist['nego' if xo==616 else 'neg']+=1
            elif xo==986:
                if rc:raise Unsupported('extsw. CR update unsupported')
                e(f'{reg(a)}=(u64)(int64_t)(s32)(u32){reg(d)};');hist['extsw']+=1
            elif xo==8:
                # subfc RT,RA,RB: RB-RA, carry=no borrow; no OE form.
                e(f'u64 sub_l_{i}={reg(a)},sub_r_{i}={reg(b)};')
                e(f'{reg(d)}=sub_r_{i}-sub_l_{i};')
                e(f'c->xer=(c->xer & ~0x20000000U) | ((sub_r_{i}>=sub_l_{i}) ? 0x20000000U : 0U);')
                if rc:record(cmp_expr(f'(int64_t){reg(d)}','0LL'))
                hist['subfc']+=1
            elif xo==235:
                # mullw: signed 32-bit result sign-extended to PPC64 GPR.
                e(f'{reg(d)}=(u64)(int64_t)(s32)(u32)((u64)(u32){reg(a)} * (u64)(u32){reg(b)});')
                if rc:record(cmp_expr(f'(int64_t){reg(d)}','0LL'))
                hist['mullw']+=1
            elif xo==457:
                # DIVDU: unsigned 64-bit quotient, guard division by zero.
                e(f'u64 divdu_divisor_{i}={reg(b)};')
                e(f'if(!divdu_divisor_{i}) return -12;')
                e(f'u64 divdu_dividend_{i}={reg(a)};')
                e(f'{reg(d)}=divdu_dividend_{i}/divdu_divisor_{i};')
                if rc:record(cmp_expr(f'(int64_t){reg(d)}','0LL'))
                hist['divdu']+=1
            elif xo==459:
                # divwu: undefined division by zero fails closed.
                e(f'u32 divisor_{i}=(u32){reg(b)};')
                e(f'if (!divisor_{i}) return -12;')
                e(f'{reg(d)}=(u64)((u32){reg(a)} / divisor_{i});')
                if rc:record(cmp_expr(f'(int64_t){reg(d)}','0LL'))
                hist['divwu']+=1
            elif xo==10:
                e(f'u64 old_{i}={reg(a)};')
                e(f'{reg(d)}=old_{i}+{reg(b)};')
                e(f'c->xer=(c->xer & ~0x20000000U) | (({reg(d)} < old_{i}) ? 0x20000000U : 0U);')
                if rc:record(cmp_expr(f'(int64_t){reg(d)}','0LL'))
                hist['addc']+=1
            elif xo in (444,266,40,28,316):
                if xo==444:e(f'{reg(a)}={reg(d)} | {reg(b)};')
                elif xo==28:e(f'{reg(a)}={reg(d)} & {reg(b)};')
                elif xo==316:e(f'{reg(a)}={reg(d)} ^ {reg(b)};')
                elif xo==266:e(f'{reg(d)}={reg(a)}+{reg(b)};')
                elif xo==40:e(f'{reg(d)}={reg(b)}-{reg(a)};')
                dest=a if xo in (444,28,316) else d
                if rc:record(cmp_expr(f'(int64_t){reg(dest)}','0LL'))
                hist['binary_xo']+=1
            elif xo in (339,467):
                spr=((w>>16)&31)|((w>>6)&0x3e0)
                if spr not in (8,9):raise Unsupported(f'unsupported SPR {spr}')
                attr='lr' if spr==8 else 'ctr'
                if xo==339:e(f'{reg(d)}=c->{attr};')
                else:e(f'c->{attr}={reg(d)};')
                hist['mfspr/mtspr']+=1
            else:raise Unsupported(f'unsupported opcode31/{xo}')
        else:raise Unsupported(f'unsupported opcode{op}')
    final=words[-1]
    final_op=(final>>26)&63
    terminal=(final_op==18 and not (final&1) or
              final_op==19 and ((final>>1)&1023) in (16,528)
              and ((final>>21)&31) in (20,21,22,23,28,29,30,31) and not (final&1))
    if not terminal:raise Unsupported('function boundary lacks unconditional terminator')
    lines.append('}')
    return '\n'.join(lines)+'\n',dict(hist)

class PPUImage:
    def __init__(self,path:Path):
        self.path=Path(path)
        self.blob=self.path.read_bytes()
        d=self.blob
        if len(d)<64 or d[:7]!=b'\x7fELF\x02\x02\x01' or struct.unpack_from('>H',d,18)[0]!=21:
            raise ValueError('not a PPU ELF64 big-endian')
        pho=struct.unpack_from('>Q',d,32)[0];ps=struct.unpack_from('>H',d,54)[0];pn=struct.unpack_from('>H',d,56)[0]
        if ps<56 or pn>256 or pho+pn*ps>len(d):raise ValueError('program headers invalid')
        self.code=[]
        for i in range(pn):
            typ,flags,off,va,pa,filesz,ms,align=struct.unpack_from('>IIQQQQQQ',d,pho+i*ps)
            if typ==1 and flags&1:
                if off+filesz>len(d):raise ValueError('truncated PT_LOAD')
                self.code.append((va,va+filesz,off))
    def words(self,start,end):
        if start>=end or start&3 or end&3 or end-start>512*4:
            raise Unsupported('invalid or oversized function range')
        for lo,hi,off in self.code:
            if lo<=start and end<=hi:
                return struct.unpack_from('>'+str((end-start)//4)+'I',self.blob,off+start-lo)
        raise Unsupported('range outside executable PT_LOAD')

def analyze_private(elf:Path,functions:list[dict],out:Path,max_output:int=8000):
    image=PPUImage(elf);ok=[];fails=Counter();hist=Counter()
    out.mkdir(parents=True,exist_ok=True)
    for f in functions:
        start,end=int(f['start'],0),int(f['end'],0)
        try:
            words=image.words(start,end)
            source,cnt=lift(words,start,f'ppu_f_{start:08x}')
            hist.update(cnt)
            if len(ok)<max_output:
                name=f'ppu_f_{start:08x}.c'
                (out/name).write_text(source)
                ok.append({'address':hex(start),'file':name,'instructions':len(words)})
        except Unsupported as ex:
            fails[str(ex).split(' at 0x')[0]]+=1
    return {'schema':'ascension-recomp/ppu-cfg-prototype-v1',
            'functions_total':len(functions),'candidates':len(ok),
            'reason_counts':dict(fails.most_common()),'emitted_ops':dict(hist),
            'note':'Experimental ISA subset; compile != semantic equivalence or game boot.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--functions',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--max-output',type=int,default=8000)
    a=p.parse_args()
    rows=json.loads(a.functions.read_text())
    report=analyze_private(a.elf,rows,a.output,a.max_output)
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('AOT CFG candidates:',report['candidates'],'/',report['functions_total'])
    print('Rejected:',list(report['reason_counts'].items())[:10])

if __name__=='__main__':main()
