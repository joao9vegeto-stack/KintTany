/* M7.20 experimental, bounded PPC64 interpreter FALLBACK for missing AOT.
 * Uses only SHA-authenticated, executable, file-backed PPC/BE ELF words.
 * Not JIT, not AOT, not full ISA. Unknown/undefined effects FAIL CLOSED.
 * The existing 1,418 native ARM64 entries always have priority.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
#include "ppu_fp_scalar.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
static int64_t sx16(uint32_t v){return (int64_t)(int16_t)(uint16_t)v;}
static uint64_t sext32(uint32_t v){return (uint64_t)(int64_t)(int32_t)v;}
static void cr_compare(ppu_context*c,unsigned bf,int result){
 const uint32_t nibble=(result<0?8u:result>0?4u:2u)|((c->xer>>31)&1u);
 const unsigned shift=(7u-bf)*4u;
 c->cr=(c->cr & ~(UINT32_C(15)<<shift)) | (nibble<<shift);
}
static void cr0(ppu_context*c,uint64_t v){
 const int64_t sign=(int64_t)v;
 cr_compare(c,0u,sign<0?-1:sign>0?1:0);
}
static int branch_cond(ppu_context*c,unsigned bo,unsigned bi,int *taken) {
 if(!taken)return AR_BAD_ARGS;
 int yes=1;
 if(!(bo&4u)){
   c->ctr--;
   yes &= (bo&2u) ? (c->ctr==0u) : (c->ctr!=0u);
 }
 if(!(bo&16u))yes &= ((c->cr>>(31u-bi))&1u)==((bo&8u)?1u:0u);
 *taken=yes;return AR_OK;
}
static uint32_t rotate32(uint32_t v,unsigned sh){
 sh&=31u;return sh?((v<<sh)|(v>>(32u-sh))):v;
}
static uint64_t rotate64(uint64_t v,unsigned sh){
 sh&=63u;return sh?((v<<sh)|(v>>(64u-sh))):v;
}
static uint32_t ppc_mask32(unsigned mb,unsigned me){
 uint32_t m=0;
 for(unsigned i=0;i<32u;i++)
   if(((i+32u-mb)%32u)<=((me+32u-mb)%32u))
      m|=UINT32_C(1)<<(31u-i);
 return m;
}
static uint64_t ppc_mask64(unsigned mb,unsigned me){
 uint64_t m=0;
 for(unsigned i=0;i<64u;i++)
   if(((i+64u-mb)%64u)<=((me+64u-mb)%64u))
      m|=UINT64_C(1)<<(63u-i);
 return m;
}
/* PPC64 word-mask behavior: for MB>ME the mask wraps across the
 * boundary and includes the high half. An M-form word rotate duplicates
 * the low 32-bit word across both halves before applying this mask.
 * Matches Power ISA and Linux powerpc sstep MASK32/DATA32 semantics. */
static uint64_t ppc_mask32_64(unsigned mb,unsigned me){
 const uint64_t lo=ppc_mask32(mb,me);
 return lo | (mb>me?UINT64_C(0xffffffff00000000):UINT64_C(0));
}
static uint64_t ppc_data32(uint32_t v){
 return (uint64_t)v | ((uint64_t)v<<32);
}
static int add_result(ppu_context*c,uint32_t pc,uint64_t v,unsigned d,unsigned record){
 c->gpr[d]=v;
 if(record)cr0(c,v);
 c->cia=pc+4u;
 return AR_TAIL;
}
int ar_ppc_fallback_step(ppu_context*c,const uint8_t*elf,size_t elf_len,
                         uint32_t pc,uint32_t *observed){
 if(observed)*observed=0u;
 if(!c||!elf||!observed||!pc||(pc&3u)||pc>UINT32_MAX-4u)
    return AR_BAD_ARGS;
 uint32_t window[6]={0};
 if(ar_m712_exec_window(elf,elf_len,pc,window)!=0 ||
    !window[4] || !(window[5]&1u))return AR_PPC_UNSUPPORTED;
 const uint32_t w=window[0],op=w>>26;
 *observed=w;
 /* Guest executable memory must still match the authenticated original.
  * Never run arbitrary mutated/PRX code as though it were owner ELF. */
 if(ar_read32(pc)!=w){
   return ar_last_error()==AR_OK?AR_PPC_UNSUPPORTED:AR_MEM_FAULT;
 }
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 const unsigned d=(w>>21)&31u,a=(w>>16)&31u,b=(w>>11)&31u;
 const int64_t imm=sx16(w);
 uint64_t *r=c->gpr;
 switch(op){
 case 48:case 50:case 52:case 54:{ /* lfs/lfd/stfs/stfd */
    const uint64_t ea=(a?r[a]:0u)+(uint64_t)imm;
    const int single=(op==48u||op==52u);
    const int rc=(op==48u||op==50u)
         ? ar_fp_load(c,d,ea,single):ar_fp_store(c,d,ea,single);
    if(rc!=AR_OK)return rc;
    ar_ppc_note_fp(pc,w);
    c->cia=pc+4u;return AR_TAIL;
 }
 case 59:{ /* fsubs PPC single-result floating subtraction */
    const unsigned xo=(w>>1)&31u;
    if((w&1u)||xo!=20u)return AR_PPC_UNSUPPORTED;
    const int rc=ar_fp_fsubs(c,d,a,b);
    if(rc!=AR_OK)return rc;
    ar_ppc_note_fp(pc,w);
    c->cia=pc+4u;return AR_TAIL;
 }
 case 63:{ /* fcfid and fdiv: PPC64 FP register bits / FPSCR */
    const unsigned xo=(w>>1)&1023u;
    if(w&1u)return AR_PPC_UNSUPPORTED; /* CR1 dot not yet implemented */
    int rc=AR_PPC_UNSUPPORTED;
    if(xo==846u && a==0u)
       rc=ar_fp_fcfid(c,d,b);
    else if(xo==18u)
        rc=ar_fp_fdiv(c,d,a,b);
     else if(xo==12u && a==0u){
         rc=ar_fp_frsp(c,d,b);
     }
     else if(xo==72u && a==0u){
        /* FMR moves all 64 raw FPR bits, including NaN and -0.0.
         * Does not modify FPSCR, CR or any guest GPR. */
        ar_fp_setraw(c,d,ar_fp_raw64(c,b));
        rc=AR_OK;
     }
    if(rc!=AR_OK)return rc;
    ar_ppc_note_fp(pc,w);
    c->cia=pc+4u;return AR_TAIL;
 }
 case 4:{ /* VMX VX: signed splat and splat-word */
   const unsigned xo=w&2047u;
   if(xo==780u||xo==844u||xo==908u){
     if(b)return AR_PPC_UNSUPPORTED; /* reserved VB bits */
     ar_vmx_splat_imm(c,d,a,xo==780u?1u:xo==844u?2u:4u);
     c->cia=pc+4u;return AR_TAIL;
   }
   if((xo&0x43fu)==44u){ /* VSLDOI VD,VA,VB,SHB: VX bits 6-9 shift */
     const unsigned shift=(w>>6)&15u;
     const int rc=ar_vmx_vsldoi(c,d,a,b,shift);
     if(rc!=AR_OK)return rc;
     c->cia=pc+4u;return AR_TAIL;
   }
   if(xo==266u && a==0u){ /* VREFP: reciprocal estimate (bounded) */
     const int rc=ar_vmx_vrefp(c,d,b);
     if(rc!=AR_OK)return rc;
     c->cia=pc+4u;return AR_TAIL;
   }
   if((xo&63u)==46u||(xo&63u)==47u){ /* VMADDfp, VNMSUBfp */
     const unsigned vc=(w>>6)&31u;
     const int rc=ar_vmx_vmaddfp(c,d,a,b,vc,(xo&63u)==47u);
     if(rc!=AR_OK)return rc;
     c->cia=pc+4u;return AR_TAIL;
   }
   if(xo==74u){ /* vsubfp VD,VA,VB: genuine M7.50 failure */
     const int rc=ar_vmx_vsubfp(c,d,a,b);
     if(rc!=AR_OK)return rc;
     c->cia=pc+4u;return AR_TAIL;
   }
   if(xo==842u){ /* VCFSX VD,VB,UIMM (scale from VA) */
      ar_vmx_vcfsx(c,d,b,a);
      c->cia=pc+4u;return AR_TAIL;
    }
    if(xo==652u){
     if(a>3u)return AR_PPC_UNSUPPORTED;
     const int rc=ar_vmx_splatw(c,d,b,a);
     if(rc!=AR_OK)return rc;
     c->cia=pc+4u;return AR_TAIL;
   }
   return AR_PPC_UNSUPPORTED;
 }
 /* M7.37 scalable PPC64 integer-immediate instruction family. */
 case 7:{ /* mulli rD,rA,SIMM: low 64 bits, modular overflow */
   const uint64_t product=r[a]*(uint64_t)imm;
   return add_result(c,pc,product,d,0u);
 }
 case 8:{ /* subfic rD,rA,SIMM: signed immediate minus 64-bit RA */
   const uint64_t right=(uint64_t)imm, left=r[a];
   const uint64_t result=right-left;
   c->xer=(c->xer&~UINT32_C(0x20000000))|
          (right>=left?UINT32_C(0x20000000):0u);
   return add_result(c,pc,result,d,0u);
 }
 case 14: return add_result(c,pc,(a?r[a]:0u)+(uint64_t)imm,d,0);
 case 15: return add_result(c,pc,(a?r[a]:0u)+(uint64_t)(imm*65536),d,0);
 case 12:case 13:{
   uint64_t x=r[a],y=(uint64_t)imm,sum=x+y;
   c->xer=(c->xer & ~UINT32_C(0x20000000)) |
          (sum<x?UINT32_C(0x20000000):0u);
   return add_result(c,pc,sum,d,op==13);
 }
 case 24:case 25:case 26:case 27:case 28:case 29:{
   const uint64_t val=(uint64_t)(w&65535u) *
                      ((op==25||op==27||op==29)?65536u:1u);
   uint64_t result=(op==24||op==25)?r[d]|val:
                   (op==26||op==27)?r[d]^val:r[d]&val;
   return add_result(c,pc,result,a,op==28||op==29);
 }
 case 10:case 11:{
   const unsigned bf=(w>>23)&7u,wide=(w>>21)&1u;
   int cmp=0;
   if(op==10){
      uint64_t left=wide?r[a]:(uint32_t)r[a],right=w&65535u;
      cmp=left<right?-1:left>right?1:0;
   } else {
      int64_t left=wide?(int64_t)r[a]:(int32_t)(uint32_t)r[a];
      cmp=left<imm?-1:left>imm?1:0;
   }
   cr_compare(c,bf,cmp);c->cia=pc+4u;return AR_TAIL;
 }
 case 32:case 34:case 40:case 36:case 38:case 44:{
   const uint64_t ea=(a?r[a]:0u)+(uint64_t)imm;
   if(op==32)r[d]=ar_read32(ea);
   if(op==34)r[d]=ar_read8(ea);
   if(op==40)r[d]=ar_read16(ea);
   if(op==36)ar_write32(ea,(uint32_t)r[d]);
   if(op==38)ar_write8(ea,(uint8_t)r[d]);
   if(op==44)ar_write16(ea,(uint16_t)r[d]);
   if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
   c->cia=pc+4u;return AR_TAIL;
 }
 case 58:case 62:{
   const unsigned ds=w&3u;
   if((op==58&&ds!=0u)||(op==62&&ds>1u)||
      (op==62&&ds==1u&&!a))return AR_PPC_UNSUPPORTED;
   const uint64_t ea=(a?r[a]:0u)+(uint64_t)(int64_t)(int16_t)(w&0xfffcu);
   if(op==58)r[d]=ar_read64(ea);else ar_write64(ea,r[d]);
   if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
   if(op==62&&ds==1u)r[a]=ea;
   c->cia=pc+4u;return AR_TAIL;
 }
 case 20:case 21:case 23:{ /* rlwimi / rlwinm / rlwnm */
   const unsigned sh=op==23u?(unsigned)r[b]&31u:(w>>11)&31u;
   const unsigned mb=(w>>6)&31u,me=(w>>1)&31u;
   const uint64_t m=ppc_mask32_64(mb,me);
   const uint64_t rotated=ppc_data32(rotate32((uint32_t)r[d],sh));
   const uint64_t v=op==20u
       ? ((r[a]&~m)|(rotated&m)) : (rotated&m);
   return add_result(c,pc,v,a,w&1u);
 }
 case 30:{ /* rldicl, rldicr, rldic, rldimi; rldcl, rldcr */
   const unsigned mb=((w>>6)&31u)|(w&32u);
   uint64_t rotated=0,mask=0,value=0;
   if(!(w&0x10u)){ /* MD form immediate shift */
     const unsigned sh=((w>>11)&31u)|((w&2u)<<4u);
     const unsigned xo=(w>>2)&3u;
     rotated=rotate64(r[d],sh);
     if(xo==0u)mask=ppc_mask64(mb,63u);
     if(xo==1u)mask=ppc_mask64(0u,mb);
     if(xo==2u||xo==3u)mask=ppc_mask64(mb,63u-sh);
     value=xo==3u ? ((r[a]&~mask)|(rotated&mask)) : (rotated&mask);
   }else{ /* MDS form with register shift */
     const unsigned sh=(unsigned)r[b]&63u;
     const unsigned xo=(w>>1)&7u;
     if(xo>1u)return AR_PPC_UNSUPPORTED;
     rotated=rotate64(r[d],sh);
     mask=xo==0u?ppc_mask64(mb,63u):ppc_mask64(0u,mb);
     value=rotated&mask;
   }
   return add_result(c,pc,value,a,w&1u);
 }
 case 31:{
   const unsigned xo=(w>>1)&1023u,record=w&1u;
   const uint64_t x=r[a],y=r[b];
   /* XS-form SRADI uses the nine-bit extension and a sixth shift bit. */
   if(((w>>2)&511u)==413u){
      const unsigned shift=b|((w&2u)<<4u);
      const uint64_t value=r[d], negative=value>>63u;
      const uint64_t removed=shift?(value&(UINT64_MAX>>(64u-shift))):0u;
      uint64_t out=shift?(value>>shift):value;
      if(negative&&shift)out|=UINT64_MAX<<(64u-shift);
      c->xer=(c->xer&~UINT32_C(0x20000000))|
         ((negative&&removed)?UINT32_C(0x20000000):0u);
      return add_result(c,pc,out,a,record);
   }
   switch(xo){
   case 278:case 246:{ /* PowerPC dcbt/dcbtst: architecturally cache-hint.
      * These are not data loads/stores: no CR/XER/GPR/memory changes and
      * no page allocation. The guest cache prefetch may be ignored by an
      * implementation; the next instruction is fetched normally.
      * Reject Rc=1 (reserved bit), including on the exact owner PC
      * 0x00525EDC (0x7C00222C) observed on physical iPhone M7.40.
      * Distinct from making UNKNOWN opcodes into no-ops: only XOs
      * explicitly defined as hints are accepted. */
      if(record)return AR_PPC_UNSUPPORTED;
      c->cia=pc+4u;
      return AR_TAIL;
   }
   case 103:case 359:case 519:case 775:
   case 551:case 807:case 231:case 487:
   case 647:case 903:case 679:case 935:{ /* VMX indexed/Cell partial */
      if(w&1u)return AR_PPC_UNSUPPORTED; /* opcode bit 0 reserved */
      const uint64_t ea=(a?r[a]:0u)+r[b];
      int vmx_rc=AR_PPC_UNSUPPORTED;
      if(xo==103u||xo==359u)vmx_rc=ar_vmx_guest_load(c,d,ea,0u);
      if(xo==519u||xo==775u)vmx_rc=ar_vmx_guest_load(c,d,ea,1u);
      if(xo==551u||xo==807u)vmx_rc=ar_vmx_guest_load(c,d,ea,2u);
      if(xo==231u||xo==487u)vmx_rc=ar_vmx_guest_store(c,d,ea,0u);
      if(xo==647u||xo==903u)vmx_rc=ar_vmx_guest_store(c,d,ea,1u);
      if(xo==679u||xo==935u)vmx_rc=ar_vmx_guest_store(c,d,ea,2u);
      if(vmx_rc!=AR_OK)return vmx_rc;
      c->cia=pc+4u;return AR_TAIL;
   }
   case 854:{ /* EIEIO: only architecturally defined exact X-form */
      if(w!=UINT32_C(0x7c0006ac))return AR_PPC_UNSUPPORTED;
      /* Conservative host-side ordering: stronger than PowerPC eieio.
       * Unlike NOP, prevents CPU reordering of future MMIO guest effects. */
      __atomic_thread_fence(__ATOMIC_SEQ_CST);
      ar_ppc_note_barrier(pc,w);
      c->cia=pc+4u;
      return AR_TAIL;
   }
   case 598:{ /* SYNC (L=0), LWSYNC (L=1); reject privileged variants */
      if(w!=UINT32_C(0x7c0004ac) &&
         w!=UINT32_C(0x7c2004ac))return AR_PPC_UNSUPPORTED;
      __atomic_thread_fence(__ATOMIC_SEQ_CST);
      ar_ppc_note_barrier(pc,w);
      c->cia=pc+4u;
      return AR_TAIL;
   }
   case 144:{ /* mtcrf FXM,rS; mtocrf L=1 selects one field */
      const unsigned fxm=(w>>12)&255u;
      const unsigned l=(w>>20)&1u;
      if((w&UINT32_C(0x00000801)) ||
         (l && (!fxm || (fxm&(fxm-1u)))))
         return AR_PPC_UNSUPPORTED; /* reserved, Rc, FXM multi-field */
      uint32_t mask=0;
      for(unsigned field=0;field<8u;field++)
         if(fxm&(0x80u>>field))
            mask|=UINT32_C(0xf0000000)>>(4u*field);
      c->cr=(c->cr&~mask)|((uint32_t)r[d]&mask);
      c->cia=pc+4u;return AR_TAIL;
   }
   case 19:{ /* mfcr rD, XFX canonical full CR copy */
      if(w!=(UINT32_C(0x7c000026)|(d<<21)))return AR_PPC_UNSUPPORTED;
      return add_result(c,pc,(uint64_t)c->cr,d,0u);
   }
   case 104:case 616:{ /* NEG / NEGO: -(RA) in 64-bit modular arithmetic */
      if(b!=0u)return AR_PPC_UNSUPPORTED; /* reserved RB must be zero */
      const uint64_t operand=x;
      const uint64_t result=UINT64_C(0)-operand; /* INT64_MIN safe */
      if(xo==616u){ /* OE: OV changes; SO is sticky */
         const uint32_t ov=operand==UINT64_C(0x8000000000000000)
             ? UINT32_C(0x40000000):0u;
         c->xer=(c->xer&~UINT32_C(0x40000000))|ov;
         if(ov)c->xer|=UINT32_C(0x80000000);
      }
      return add_result(c,pc,result,d,record);
   }
   case 457:{ /* divdu: unsigned PPC64 quotient, no overflow form */
      if(!y)return AR_PPC_UNSUPPORTED; /* undefined divisor zero */
      return add_result(c,pc,x/y,d,record);
   }
   case 459:{ /* divwu: unsigned low 32, ZERO extended to 64 */
      const uint32_t divisor=(uint32_t)y;
      if(!divisor)return AR_PPC_UNSUPPORTED; /* architecturally undefined */
      return add_result(c,pc,(uint32_t)x/divisor,d,record);
   }
   case 75:{ /* M7.36 mulhw: signed 32x32, high 32, sign extend PPC64 */
      const int64_t p=(int64_t)(int32_t)(uint32_t)x *
                      (int64_t)(int32_t)(uint32_t)y;
      const uint32_t upper=(uint32_t)((uint64_t)p>>32u);
      /* x/y are saved before writing d: RT may alias RA or RB. */
      return add_result(c,pc,sext32(upper),d,record);
   }
   case 9:case 73:{ /* mulhdu / mulhd: genuine high 64-bit PPC64 */
      const unsigned __int128 wide=(unsigned __int128)x*
                                   (unsigned __int128)y;
      uint64_t high=(uint64_t)(wide>>64u);
      if(xo==73u){ /* two's-complement signed high half */
        if(x>>63u)high-=y;
        if(y>>63u)high-=x;
      }
      return add_result(c,pc,high,d,record);
   }
   case 233:{ /* mulld: low 64-bit modular signed product */
      return add_result(c,pc,x*y,d,record);
   }
   case 235:{ /* mullw: low 32 of 32x32 product, signed word result */
      const uint32_t v=(uint32_t)((uint64_t)(uint32_t)x*(uint32_t)y);
      return add_result(c,pc,sext32(v),d,record);
   }
   case 8:{ /* subfc: RB - RA; CA=no borrow */
      const uint64_t result=y-x;
      c->xer=(c->xer & ~UINT32_C(0x20000000))|
              (y>=x?UINT32_C(0x20000000):0u);
      return add_result(c,pc,result,d,record);
   }
   case 10:{
      const uint64_t result=x+y;
      c->xer=(c->xer & ~UINT32_C(0x20000000))|
              (result<x?UINT32_C(0x20000000):0u);
      return add_result(c,pc,result,d,record);
   }
   case 40:return add_result(c,pc,y-x,d,record);
   case 266:return add_result(c,pc,x+y,d,record);
   /* M7.42: general PowerPC64 logical register family. These are X-form
    * operations: RS is field d, RA is destination a, RB is b. Capture
    * both source operands BEFORE writing RA (RA may alias RS or RB).
    * The caller retains the CR/XER/LR/CTR ABI semantics: only Rc=1
    * updates CR0, and none of these logical instructions touch XER. */
   case 124:case 476:case 284:case 412:case 60:{
      const uint64_t rs=r[d],rb=r[b];
      const uint64_t result=
          xo==124u?~(rs|rb):  /* nor */
          xo==476u?~(rs&rb):  /* nand */
          xo==284u?~(rs^rb):  /* eqv */
          xo==412u?(rs|~rb):  /* orc */
                    (rs&~rb); /* andc */
      return add_result(c,pc,result,a,record);
   }
   case 58:{ /* cntlzd RA,RS: count leading zeroes in 64-bit RS */
      if(b!=0u)return AR_PPC_UNSUPPORTED; /* RB field must be zero */
      const uint64_t rs=r[d];
      const uint64_t count=rs?(uint64_t)__builtin_clzll((unsigned long long)rs):64u;
      return add_result(c,pc,count,a,record);
   }
   case 444:return add_result(c,pc,r[d]|r[b],a,record);
   case 28:return add_result(c,pc,r[d]&r[b],a,record);
   case 316:return add_result(c,pc,r[d]^r[b],a,record);
   case 0:case 32:{
      const unsigned bf=(w>>23)&7u,wide=(w>>21)&1u;
      int res=0;
      if(xo==0){
         const int64_t u=wide?(int64_t)x:(int32_t)(uint32_t)x;
         const int64_t v=wide?(int64_t)y:(int32_t)(uint32_t)y;
         res=u<v?-1:u>v?1:0;
      } else {
         const uint64_t u=wide?x:(uint32_t)x,v=wide?y:(uint32_t)y;
         res=u<v?-1:u>v?1:0;
      }
      cr_compare(c,bf,res);c->cia=pc+4u;return AR_TAIL;
   }
   case 339:case 467:{
      const unsigned spr=((w>>16)&31u)|((w>>6)&0x3e0u);
      if(spr!=8u&&spr!=9u)return AR_PPC_UNSUPPORTED;
      uint64_t *value=spr==8u?&c->lr:&c->ctr;
      if(xo==339)r[d]=*value;else *value=r[d];
      c->cia=pc+4u;return AR_TAIL;
   }
   case 23:case 87:case 279:case 21:case 151:case 215:case 407:case 149:{
      const uint64_t ea=(a?r[a]:0u)+r[b];
      if(xo==23)r[d]=ar_read32(ea);
      if(xo==87)r[d]=ar_read8(ea);
      if(xo==279)r[d]=ar_read16(ea);
      if(xo==21)r[d]=ar_read64(ea);
      if(xo==151)ar_write32(ea,(uint32_t)r[d]);
      if(xo==215)ar_write8(ea,(uint8_t)r[d]);
      if(xo==407)ar_write16(ea,(uint16_t)r[d]);
      if(xo==149)ar_write64(ea,r[d]);
      if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
      c->cia=pc+4u;return AR_TAIL;
   }
   case 536:{ /* SRW PPC logical low-word shift by RB 6-bit value. */
      const unsigned sh=(unsigned)r[b]&63u;
      const uint32_t val=(uint32_t)r[d];
      return add_result(c,pc,sh>=32u?0u:(uint64_t)(val>>sh),a,record);
   }
   case 824:{ /* srawi RA,RS,SH: arithmetic signed word shift */
      const unsigned sh=b;
      const uint32_t input=(uint32_t)r[d];
      const int negative=(input&UINT32_C(0x80000000))!=0;
      uint32_t shifted=input>>sh;
      if(negative && sh)shifted|=UINT32_MAX<<(32u-sh);
      const int carry=negative && sh && ((input&((UINT32_C(1)<<sh)-1u))!=0u);
      c->xer=(c->xer & ~UINT32_C(0x20000000)) |
             (carry?UINT32_C(0x20000000):0u);
      return add_result(c,pc,sext32(shifted),a,record);
   }
   case 954:case 922:case 986:{
      uint64_t val=xo==954?(uint64_t)(int64_t)(int8_t)(uint8_t)r[d]:
                   xo==922?(uint64_t)(int64_t)(int16_t)(uint16_t)r[d]:
                            sext32((uint32_t)r[d]);
      return add_result(c,pc,val,a,record);
   }
   case 26:{
      const uint32_t v=(uint32_t)r[d];
      return add_result(c,pc,v?(uint64_t)__builtin_clz(v):32u,a,record);
   }
   default:return AR_PPC_UNSUPPORTED;
   }
 }
 case 18:case 16:{
   int64_t disp=0;
   if(op==18){
     disp=(int64_t)(w&UINT32_C(0x03fffffc));
     if(disp & INT64_C(0x02000000))disp-=INT64_C(0x04000000);
   } else disp=(int16_t)(w&UINT32_C(0xfffc));
   const int64_t dest=(w&2u)?disp:((int64_t)pc+disp);
   if(dest<0||dest>UINT32_MAX||(dest&3))return AR_PPC_UNSUPPORTED;
   int taken=1;
   if(op==16)branch_cond(c,d,(w>>16)&31u,&taken);
   const uint32_t fall=pc+4u;
   if(w&1u){
     c->lr=fall;
     if(taken){
       const int rc=ar_guest_call(c,(uint64_t)dest);
       if(rc!=AR_OK){ar_ppc_note_failed_call(pc,(uint32_t)dest);return rc;}
     }
     c->cia=fall;return AR_TAIL;
   }
   c->cia=taken?(uint32_t)dest:fall;return AR_TAIL;
 }
 case 19:{
   const unsigned xo=(w>>1)&1023u,bo=d,bi=(w>>16)&31u;
   if(xo==150u){ /* ISYNC: instruction synchronization */
      if(w!=UINT32_C(0x4c00012c))return AR_PPC_UNSUPPORTED;
      __atomic_thread_fence(__ATOMIC_SEQ_CST);
      ar_ppc_note_barrier(pc,w);
      c->cia=pc+4u;
      return AR_TAIL;
   }
   if(xo!=16u&&xo!=528u)return AR_PPC_UNSUPPORTED;
   if(xo==528u&&!(bo&4u))return AR_PPC_UNSUPPORTED;
   const uint64_t target=(xo==16u?c->lr:c->ctr)&~UINT64_C(3);
   int taken=1;
   branch_cond(c,bo,bi,&taken);
   if(w&1u){
      c->lr=pc+4u;
      if(taken){
        const int rc=ar_guest_call(c,target);
        if(rc!=AR_OK){ar_ppc_note_failed_call(pc,(uint32_t)target);return rc;}
      }
      c->cia=pc+4u;return AR_TAIL;
   }
   if(!taken){c->cia=pc+4u;return AR_TAIL;}
   c->cia=target;
   return xo==16u?AR_OK:AR_TAIL;
 }
 case 17:{
   /* Power ISA valid 32-bit syscall encoding only; never allow undefined forms. */
   if(w!=UINT32_C(0x44000002))return AR_PPC_UNSUPPORTED;
   ar_ppc_note_syscall_pc(pc); /* preserve the exact guest instruction address */
   const int rc=ar_guest_syscall(c);
   if(rc!=AR_OK)return rc;
   c->cia=pc+4u;return AR_TAIL;
 }
 default:return AR_PPC_UNSUPPORTED;
 }
}
