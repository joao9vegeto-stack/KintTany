/* M7.1: interpreter fallback inside the already-signed native PPU binary.
 * This is NOT AOT recompilation. No JIT, executable guest mapping or NOP
 * fallback; unknown ISA / HLE / memory returns a concrete fault. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "ppu_bridge.h"

extern int ar_private_import_match(const uint8_t*,size_t,uint32_t,uint32_t[4],char[48]);
extern int ar_ppu_rldicl(uint32_t,uint64_t,uint64_t*);

typedef struct {uint64_t va,end;uint32_t flags;} ar71seg;
static uint16_t rd16(const uint8_t*p){return ((uint16_t)p[0]<<8)|p[1];}
static uint32_t rd32(const uint8_t*p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint64_t rd64(const uint8_t*p){return ((uint64_t)rd32(p)<<32)|rd32(p+4);}
static int executable(const ar71seg*s,unsigned n,uint64_t pc){
 if(pc>UINT32_MAX || (pc&3u))return 0;
 for(unsigned i=0;i<n;i++)
   if((s[i].flags&1u) && pc>=s[i].va && pc+4u<=s[i].end)return 1;
 return 0;
}
static void guest_cr0(ppu_context*c,uint64_t v){
 const int64_t signedv=(int64_t)v;
 const unsigned value=(signedv<0?8u:(signedv>0?4u:2u))|
                      ((c->xer>>31)&1u);
 c->cr=(c->cr&0x0fffffffu)|(value<<28);
}
/* M7.2: architecture-wide compares update ONLY the selected CR field.
 * Each 4-bit nibble is LT,GT,EQ,SO, with BF0 in the top nibble. */
static void guest_compare(ppu_context*c,unsigned bf,unsigned is_signed,
                          unsigned wide,uint64_t lhs,uint64_t rhs){
 unsigned cmp;
 if(is_signed){
   if(wide){
     const int64_t a=(int64_t)lhs,b=(int64_t)rhs;
     cmp=a<b?8u:(a>b?4u:2u);
   }else{
     const int32_t a=(int32_t)(uint32_t)lhs,b=(int32_t)(uint32_t)rhs;
     cmp=a<b?8u:(a>b?4u:2u);
   }
 }else{
   const uint64_t a=wide?lhs:(uint32_t)lhs;
   const uint64_t b=wide?rhs:(uint32_t)rhs;
   cmp=a<b?8u:(a>b?4u:2u);
 }
 cmp|=(unsigned)((c->xer>>31)&1u);
 const unsigned shift=28u-4u*bf;
 c->cr=(c->cr&~(15u<<shift))|(cmp<<shift);
}
/* BO bits: 0x10 suppresses CR check, 0x08 selects CR=true,
 * 0x04 suppresses CTR decrement, 0x02 selects CTR==0.
 * BI is numbered MSB-first across the 32-bit CR. */
static int guest_branch_test(ppu_context*c,unsigned bo,unsigned bi,
                             unsigned ctr_may_decrement,int*taken){
 if(!(bo&4u)){
   if(!ctr_may_decrement)return -1; /* bcctr decrement form is invalid */
   c->ctr--;
 }
 const int count_ok=(bo&4u) ||
            (((c->ctr!=0u)?1:0)!=((bo&2u)?1:0));
 const int crbit=(int)((c->cr>>(31u-bi))&1u);
 const int cond_ok=(bo&16u)||(crbit==((bo&8u)?1:0));
 *taken=count_ok && cond_ok;
 return 0;
}

/* Diagnostic fields:
 [0] steps, [1] final PC, [2] last opcode, [3] stop reason,
 [4] native HLE calls, [5] TLS r13, [6] CTR, [7] LR,
 [8] r1, [9] r2, [10] unresolved NID, [11] memory EA / syscall,
 [12] last completed PC, [13] indirect calls/returns,
 [14] guest branch count, [15] budget.
 Returns -1310 on budget exhaustion, -1311 on unsupported ISA,
 -1312 invalid executable target, -1313 memory fault, -1314 unknown
 import/indirect target, -1315 HLE failure, -1316 invalid ELF/ABI.
 */
int ar_m71_signed_ppu_interpret(const uint8_t*d,size_t len,ppu_context*c,
                uint32_t guest_stub,uint32_t toc,
                uint32_t budget,uint32_t out[16]){
 if(!out)return -1316;
 memset(out,0,16u*sizeof(*out));
 if(!d||!c||len<64u||budget==0u||budget>8192u||
    memcmp(d,"\177ELF",4)||d[4]!=2u||d[5]!=2u||d[6]!=1u ||
    rd16(d+18)!=21u)return -1316;
 const uint64_t phoff=rd64(d+32);
 const unsigned stride=rd16(d+54),count=rd16(d+56);
 if(stride<56u||!count||count>64u||phoff>len||
    (uint64_t)stride*count>len-phoff)return -1316;
 ar71seg seg[64]={0};unsigned used=0;
 for(unsigned j=0;j<count;j++){
    const uint8_t*p=d+phoff+(uint64_t)j*stride;
    if(rd32(p)!=1u)continue;
    const uint64_t va=rd64(p+16),fs=rd64(p+32),off=rd64(p+8);
    if(va>UINT32_MAX||fs>UINT32_MAX-va||
       off>len||fs>len-off)return -1316;
    if(fs)seg[used++]=(ar71seg){va,va+fs,rd32(p+4)};
 }
 if(!used)return -1316;
 uint32_t nid=0;char lib[48]={0};uint32_t im[4]={0};
 if(guest_stub &&
    ar_private_import_match(d,len,guest_stub,im,lib)==0 &&
    im[0]==0x744680a2u && im[1]==guest_stub &&
    strcmp(lib,"sysPrxForUser")==0)nid=im[0];
 out[10]=nid;out[15]=budget;
 int rc=-1310;
 uint64_t fail_ea=0;
 uint32_t lastpc=0;
 for(uint32_t i=0;i<budget;i++){
   const uint64_t pc=c->cia;
   if(!executable(seg,used,pc)){rc=-1312;break;}
   const uint32_t word=ar_read32(pc),op=word>>26;
   if(ar_last_error()!=AR_OK){rc=-1313;fail_ea=pc;break;}
   out[1]=(uint32_t)pc;out[2]=word;
   const unsigned rt=(word>>21)&31u,ra=(word>>16)&31u;
   const unsigned rb=(word>>11)&31u;
   const int64_t imm=(int16_t)(word&0xffffu);
   uint64_t next=pc+4u;
   if(op==14u){ /* addi */
     c->gpr[rt]=(ra?c->gpr[ra]:0u)+(uint64_t)imm;
   }else if(op==15u){ /* addis */
     c->gpr[rt]=(ra?c->gpr[ra]:0u)+((uint64_t)imm<<16);
   }else if(op==24u||op==25u){ /* ori / oris */
     c->gpr[ra]=c->gpr[rt]|
         ((uint64_t)(word&0xffffu)<<(op==25u?16u:0u));
   }else if(op==26u||op==27u){ /* xori / xoris */
     c->gpr[ra]=c->gpr[rt]^
         ((uint64_t)(word&0xffffu)<<(op==27u?16u:0u));
   }else if(op==28u){ /* andi. includes CR0 update */
     c->gpr[ra]=c->gpr[rt]&(word&0xffffu);
     guest_cr0(c,c->gpr[ra]);
   }else if(op==10u||op==11u){ /* cmpli / cmpi: unsigned/signed immediate */
     if(word&0x00400000u){rc=-1311;break;} /* reserved bit 22 */
     const unsigned bf=(word>>23)&7u,wide=(word>>21)&1u;
     const uint64_t rhs=op==10u?(uint16_t)word:(uint64_t)(int64_t)(int16_t)word;
     guest_compare(c,bf,op==11u,wide,c->gpr[ra],rhs);
   }else if(op==32u||op==58u){ /* lwz / ld */
     if(op==58u&&((word&3u)!=0u||!ra)){rc=-1311;break;}
     const uint64_t ea=(ra?c->gpr[ra]:0u)+
                (uint64_t)(op==58u?(int16_t)(word&0xfffcu):imm);
     const uint64_t v=op==32u?ar_read32(ea):ar_read64(ea);
     if(ar_last_error()!=AR_OK){rc=-1313;fail_ea=ea;break;}
     c->gpr[rt]=v;
   }else if(op==36u||op==62u){ /* stw / std / stdu */
     if(op==62u&&(!ra || (word&3u)>1u)){rc=-1311;break;}
     const uint64_t ea=(ra?c->gpr[ra]:0u)+
                (uint64_t)(op==62u?(int16_t)(word&0xfffcu):imm);
     if(op==36u)ar_write32(ea,(uint32_t)c->gpr[rt]);
     else ar_write64(ea,c->gpr[rt]);
     if(ar_last_error()!=AR_OK){rc=-1313;fail_ea=ea;break;}
     if(op==62u && (word&3u))c->gpr[ra]=ea;
   }else if(op==30u){ /* exact rldicl only */
     uint64_t val=0;
     if(ar_ppu_rldicl(word,c->gpr[rt],&val)){rc=-1311;break;}
     c->gpr[ra]=val;
   }else if(op==31u &&
             (((word>>1)&1023u)==0u || ((word>>1)&1023u)==32u)){
     /* cmp / cmpl register, BF=CR field and L=64-bit selector. */
     if(word&0x00400001u){rc=-1311;break;} /* reserved bit or Rc */
     const unsigned bf=(word>>23)&7u,wide=(word>>21)&1u;
     guest_compare(c,bf,((word>>1)&1023u)==0u,
                   wide,c->gpr[ra],c->gpr[rb]);
   }else if(op==16u){ /* bc / bcl: CR, CTR and AA/LK semantics */
     const unsigned bo=(word>>21)&31u,bi=(word>>16)&31u;
     int taken=0;
     if(guest_branch_test(c,bo,bi,1u,&taken)){rc=-1311;break;}
     if(word&1u)c->lr=next; /* LK applies even when branch not taken */
     if(taken){
       const int64_t delta=(int16_t)(word&0xfffcu);
       const int64_t dest=(word&2u)?delta:((int64_t)pc+delta);
       if(dest<0 || !executable(seg,used,(uint64_t)dest)){rc=-1312;break;}
       next=(uint64_t)dest;out[14]++;
     }
   }else if(op==18u){ /* b/bl + AA */
     int64_t delta=(int64_t)(word&0x03fffffcu);
     if(delta&0x02000000)delta-=0x04000000;
     const int64_t dest=(word&2u)?delta:((int64_t)pc+delta);
     if(dest<0 || !executable(seg,used,(uint64_t)dest)){rc=-1312;break;}
     if(word&1u)c->lr=next;
     next=(uint64_t)dest;out[14]++;
   }else if(op==19u && ((word>>1)&1023u)==16u){ /* bclr: CR and LR */
     const unsigned bo=(word>>21)&31u,bi=(word>>16)&31u;
     int taken=0;
     if(guest_branch_test(c,bo,bi,1u,&taken)){rc=-1311;break;}
     const uint64_t target=c->lr&~UINT64_C(3);
     if(word&1u)c->lr=next; /* bclrl updates LR even if not taken */
     if(taken){
       if(!executable(seg,used,target)){rc=-1312;break;}
       next=target;out[13]++;
     }
   }else if(op==19u && ((word>>1)&1023u)==528u){ /* bcctr: CR and CTR */
     const unsigned bo=(word>>21)&31u,bi=(word>>16)&31u;
     int taken=0;
     if(guest_branch_test(c,bo,bi,0u,&taken)){rc=-1311;break;}
     const uint64_t target=c->ctr&~UINT64_C(3);
     if(word&1u)c->lr=next;
     if(taken && executable(seg,used,target)){
       next=target;out[13]++;
     }else if(taken && (word&1u) && word==0x4e800421u &&
              nid && c->gpr[12]==guest_stub &&
              (uint32_t)c->ctr==ar_read32(guest_stub) &&
              (uint32_t)c->gpr[2]==ar_read32((uint64_t)guest_stub+4u) &&
              ar_last_error()==AR_OK){
       /* Only the actual private PRX import can reach native TLS HLE. */
       const int hle=ar_run(c,guest_stub,32u);
       if(hle!=AR_OK){rc=-1315;fail_ea=(uint32_t)hle;break;}
       c->gpr[2]=toc;
       out[4]++;out[13]++;
     }else if(taken){rc=-1314;fail_ea=target;break;}
   }else if(op==31u && ((word>>1)&1023u)==444u && !(word&1u)){
     c->gpr[ra]=c->gpr[rt]|c->gpr[rb]; /* or / mr */
   }else if(op==31u && ((word>>1)&1023u)==339u && !(word&1u)){
     const unsigned enc=(word>>11)&1023u;
     const unsigned spr=((enc&31u)<<5)|(enc>>5);
     if(spr==8u)c->gpr[rt]=c->lr;
     else if(spr==9u)c->gpr[rt]=c->ctr;
     else {rc=-1311;break;}
   }else if(op==31u && ((word>>1)&1023u)==467u && !(word&1u)){
     const unsigned enc=(word>>11)&1023u;
     const unsigned spr=((enc&31u)<<5)|(enc>>5);
     if(spr==8u)c->lr=c->gpr[rt];
     else if(spr==9u)c->ctr=c->gpr[rt];
     else {rc=-1311;break;}
   }else if(op==17u){ /* LV2 syscall unimplemented: report number, not fake OK */
     rc=-1314;fail_ea=c->gpr[11];break;
   }else{rc=-1311;break;}
   lastpc=(uint32_t)pc;
   c->cia=next;
   out[0]++;out[1]=(uint32_t)next;
 }
 out[3]=(uint32_t)rc;out[5]=(uint32_t)c->gpr[13];
 out[6]=(uint32_t)c->ctr;out[7]=(uint32_t)c->lr;
 out[8]=(uint32_t)c->gpr[1];out[9]=(uint32_t)c->gpr[2];
 out[11]=(uint32_t)fail_ea;out[12]=lastpc;
 return rc;
}
