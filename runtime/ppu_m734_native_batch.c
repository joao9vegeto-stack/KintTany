/* M7.34 owner trace-driven AOT batch, authored from executable branches
 * actually reached by NPUA80918. ELF original is NOT included here.
 * This module is linked as ARM64, never treats interpreted instructions as
 * native coverage. Existing private whole-ELF SHA gate must succeed first.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define CA UINT32_C(0x20000000)
static uint64_t sx32(uint32_t v){return (uint64_t)(int64_t)(int32_t)v;}
static void cr_cmp7(ppu_context*c,uint32_t l,uint32_t r){
 const int32_t a=(int32_t)l,b=(int32_t)r;
 const uint32_t f=a<b?8u:a>b?4u:2u;
 c->cr=(c->cr&~UINT32_C(0xf))|f|((c->xer>>31)&1u);
}
static void cr_cmp6(ppu_context*c,uint32_t l,uint32_t r){
 const int32_t a=(int32_t)l,b=(int32_t)r;
 const uint32_t f=a<b?8u:a>b?4u:2u;
 c->cr=(c->cr&~UINT32_C(0xf0))|
       (f<<4)|(((c->xer>>31)&1u)<<4);
}
static uint64_t sraw32(ppu_context*c,uint64_t value,unsigned sh){
 const uint32_t src=(uint32_t)value;
 const uint32_t sign=src>>31;
 uint32_t out=src>>sh;
 if(sign&&sh)out|=UINT32_MAX<<(32u-sh);
 const uint32_t dropped=sh?(src&((UINT32_C(1)<<sh)-1u)):0;
 c->xer=(c->xer&~CA)|((sign&&dropped)?CA:0);
 return sx32(out);
}
static int be_store64(uint64_t ea,uint64_t val){
 ar_write64(ea,val);
 return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;
}
static int be_store32(uint64_t ea,uint32_t val){
 ar_write32(ea,val);
 return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;
}
int ar_m734_native_0052aa18(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 c->gpr[0]=UINT64_C(0x18450000);c->cia=UINT32_C(0x0052aa1c);
 return AR_TAIL;
}
int ar_m734_native_0052aa90(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 c->gpr[31]-=UINT64_C(1);c->cia=UINT32_C(0x0052aa94);
 return AR_TAIL;
}
int ar_m734_native_0052aa94(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 c->gpr[3]=sx32((uint32_t)c->gpr[31]);c->gpr[4]=0;
 c->lr=UINT32_C(0x0052aaa0);
 const int rc=ar_guest_call(c,UINT32_C(0x0052a910));
 if(rc!=AR_OK){ar_ppc_note_failed_call(0x0052aa9c,0x0052a910);return rc;}
 c->cia=UINT32_C(0x0052aaa0);
 return AR_TAIL;
}
int ar_m734_native_0052a9a0(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 const uint64_t oldsp=r[1],sp=oldsp-UINT64_C(176);
 if(be_store64(sp,oldsp)!=AR_OK)return AR_MEM_FAULT;
 r[1]=sp;
 r[0]=c->lr;
 cr_cmp7(c,(uint32_t)r[3],0u);
 if(be_store64(sp+192u,r[0])!=AR_OK)return AR_MEM_FAULT;
 r[0]=UINT64_C(32384);
 if(be_store64(sp+168u,r[31])!=AR_OK)return AR_MEM_FAULT;
 r[0]|=UINT64_C(33706)<<16;
 if(be_store64(sp+128u,r[26])!=AR_OK)return AR_MEM_FAULT;
 if(be_store64(sp+136u,r[27])!=AR_OK)return AR_MEM_FAULT;
 if(be_store64(sp+144u,r[28])!=AR_OK)return AR_MEM_FAULT;
 if(be_store64(sp+152u,r[29])!=AR_OK)return AR_MEM_FAULT;
 if(be_store64(sp+160u,r[30])!=AR_OK)return AR_MEM_FAULT;
 r[11]=r[5];
 r[31]=r[4]+r[0];
 c->cia=(c->cr&2u)?UINT32_C(0x0052abf0):UINT32_C(0x0052a9dc);
 return AR_TAIL;
}
int ar_m734_native_0052abf0(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 c->gpr[9]=c->gpr[13];
 c->gpr[3]=c->gpr[9]-UINT64_C(28424);
 c->cia=UINT32_C(0x0052a9dc);
 return AR_TAIL;
}
int ar_m734_native_0052a9dc(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 r[28]=(uint32_t)r[3];
 cr_cmp7(c,(uint32_t)r[11],0);
 r[27]=r[31];
 if(be_store32(r[28]+32u,(uint32_t)r[5])!=AR_OK)return AR_MEM_FAULT;
 c->cia=(c->cr&2u)?UINT32_C(0x0052aa18):UINT32_C(0x0052a9f0);
 return AR_TAIL;
}
int ar_m734_native_0052a9f0(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 r[3]=r[1]+UINT64_C(112);
 r[4]=r[1]+UINT64_C(116);
 r[11]=UINT64_C(144);
 ar_ppc_note_syscall_pc(UINT32_C(0x0052a9fc));
 const int rc=ar_guest_syscall(c);
 if(rc!=AR_OK)return rc;
 c->cia=UINT32_C(0x0052aa00);
 return AR_TAIL;
}
int ar_m734_native_0052aa00(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 r[29]=ar_read32(r[1]+116u);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 r[0]=((uint32_t)r[29]<<6u);
 r[29]=((uint32_t)r[29]<<2u);
 r[0]-=r[29];
 r[0]=sx32((uint32_t)r[0]);
 r[27]=r[31]+r[0];
 c->cia=UINT32_C(0x0052aa18);
 return AR_TAIL;
}
int ar_m734_native_0052aaa0(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 r[3]+=r[29];
 r[29]-=UINT64_C(365);
 cr_cmp7(c,(uint32_t)r[30],(uint32_t)r[3]);
 c->cia=(c->cr&2u)?UINT32_C(0x0052aa90):UINT32_C(0x0052aab0);
 return AR_TAIL;
}
int ar_m734_native_0052a910(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 cr_cmp6(c,(uint32_t)r[3],0);
 r[0]=r[3]-UINT64_C(1);
 r[10]=r[4];
 r[11]=sraw32(c,r[0],2);
 const uint64_t carry=(c->xer&CA)?1u:0u;
 const uint64_t original=r[11];
 r[11]+=carry; /* addze r11,r11; update CA to 64-bit carry-out */
 c->xer=(c->xer&~CA)|((carry&&original==UINT64_MAX)?CA:0u);
 /* PPC BF25: branch when CR6.GT is false. */
 c->cia=(c->cr & UINT32_C(0x40))?
          UINT32_C(0x0052a928):UINT32_C(0x0052a960);
 return AR_TAIL;
}
typedef int (*block_fn)(ppu_context*);
struct validated_block {
 uint32_t pc,n;
 uint64_t fnv;
 block_fn fn;
};
static const struct validated_block blocks[]={
 {UINT32_C(0x0052aa18),1,UINT64_C(0xcdb6b91b938e215a),ar_m734_native_0052aa18},
 {UINT32_C(0x0052aa90),1,UINT64_C(0xa31b7040905213cd),ar_m734_native_0052aa90},
 {UINT32_C(0x0052aa94),3,UINT64_C(0x17ea3e94d52b53b7),ar_m734_native_0052aa94},
 {UINT32_C(0x0052a9a0),15,UINT64_C(0x028d5cdeeb47ad52),ar_m734_native_0052a9a0},
 {UINT32_C(0x0052abf0),3,UINT64_C(0x5ea958524a1978af),ar_m734_native_0052abf0},
 {UINT32_C(0x0052a9dc),5,UINT64_C(0x528906bc02c5e4a9),ar_m734_native_0052a9dc},
 {UINT32_C(0x0052a9f0),4,UINT64_C(0xe781d8056682199a),ar_m734_native_0052a9f0},
 {UINT32_C(0x0052aa00),6,UINT64_C(0xa8ea07163ccd1d8e),ar_m734_native_0052aa00},
 {UINT32_C(0x0052aaa0),4,UINT64_C(0xd469a8248ad57a0a),ar_m734_native_0052aaa0},
 {UINT32_C(0x0052a910),6,UINT64_C(0x1978630d99cf26b0),ar_m734_native_0052a910}
};
/* Full private ELF SHA is previously authenticated on device. Independently
 * check each source word comes from PT_LOAD X and matches guest VM bytes.
 * All windows validated before registering any of these ten AOT entries. */
int ar_m734_register_batch(const uint8_t *elf,size_t length){
 if(!elf||length<64)return AR_BAD_ARGS;
 for(size_t i=0;i<sizeof(blocks)/sizeof(blocks[0]);i++){
  const struct validated_block*b=&blocks[i];
  uint64_t hash=UINT64_C(14695981039346656037);
  for(uint32_t j=0;j<b->n;j+=4u){
   uint32_t words[6]={0};
   const uint32_t need=(b->n-j)<4u?(b->n-j):4u;
   if(ar_m712_exec_window(elf,length,b->pc+j*4u,words)!=AR_OK||
      words[4]<need||!(words[5]&1u))return AR_BAD_ARGS;
   for(uint32_t k=0;k<need;k++){
    const uint32_t w=words[k];
    if(ar_read32(b->pc+(j+k)*4u)!=w||ar_last_error()!=AR_OK)
       return AR_BAD_ARGS;
    for(unsigned q=0;q<4u;q++){
      hash^=(uint8_t)(w>>(24u-8u*q));
      hash*=UINT64_C(1099511628211);
    }
   }
  }
  if(hash!=b->fnv)return AR_BAD_ARGS;
 }
 for(size_t i=0;i<sizeof(blocks)/sizeof(blocks[0]);i++){
   const int rc=ar_register(blocks[i].pc,blocks[i].fn);
   if(rc!=AR_OK)return rc;
 }
 return AR_OK;
}
