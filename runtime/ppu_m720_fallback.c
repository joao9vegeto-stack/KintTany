/* M7.20 experimental, bounded PPC64 interpreter FALLBACK for missing AOT.
 * Uses only SHA-authenticated, executable, file-backed PPC/BE ELF words.
 * Not JIT, not AOT, not full ISA. Unknown/undefined effects FAIL CLOSED.
 * The existing 1,418 native ARM64 entries always have priority.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
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
   switch(xo){
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
   case 459:{ /* divwu: unsigned low 32, ZERO extended to 64 */
      const uint32_t divisor=(uint32_t)y;
      if(!divisor)return AR_PPC_UNSUPPORTED; /* architecturally undefined */
      return add_result(c,pc,(uint32_t)x/divisor,d,record);
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
       if(rc!=AR_OK)return rc;
     }
     c->cia=fall;return AR_TAIL;
   }
   c->cia=taken?(uint32_t)dest:fall;return AR_TAIL;
 }
 case 19:{
   const unsigned xo=(w>>1)&1023u,bo=d,bi=(w>>16)&31u;
   if(xo!=16u&&xo!=528u)return AR_PPC_UNSUPPORTED;
   if(xo==528u&&!(bo&4u))return AR_PPC_UNSUPPORTED;
   const uint64_t target=(xo==16u?c->lr:c->ctr)&~UINT64_C(3);
   int taken=1;
   branch_cond(c,bo,bi,&taken);
   if(w&1u){
      c->lr=pc+4u;
      if(taken){
        const int rc=ar_guest_call(c,target);
        if(rc!=AR_OK)return rc;
      }
      c->cia=pc+4u;return AR_TAIL;
   }
   if(!taken){c->cia=pc+4u;return AR_TAIL;}
   c->cia=target;
   return xo==16u?AR_OK:AR_TAIL;
 }
 case 17:{
   const int rc=ar_guest_syscall(c);
   if(rc!=AR_OK)return rc;
   c->cia=pc+4u;return AR_TAIL;
 }
 default:return AR_PPC_UNSUPPORTED;
 }
}
