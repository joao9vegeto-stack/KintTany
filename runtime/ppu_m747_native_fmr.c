/* M7.47: static ARM64 translation of authentic GOWA.ELF FP frontier.
 * No JIT, RPCS3 engine, or game data included in this module.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t[6]);
static void fmr(ppu_context*c,unsigned dst,unsigned src){
 uint64_t bits;memcpy(&bits,&c->fpr[src],8u);memcpy(&c->fpr[dst],&bits,8u);
}
int ar_m747_native_003eef0c(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 fmr(c,1,31);fmr(c,2,31);fmr(c,3,31);
 c->lr=UINT32_C(0x003eef1c);
 const int rc=ar_guest_call(c,UINT32_C(0x003e5a54));
 if(rc!=AR_OK)return rc;
 c->cia=UINT32_C(0x003eef1c);return AR_TAIL;
}
int ar_m747_native_003eef20(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 r[3]=UINT64_C(0x009d0000);r[4]=UINT64_C(0x00680000);
 fmr(c,1,31);r[5]=0;
 fmr(c,2,31);r[8]=0;fmr(c,3,31);
 const uint64_t l3=r[3];
 r[3]+=(uint64_t)(int64_t)(int16_t)UINT16_C(0xb228);
 c->xer=(c->xer&~UINT32_C(0x20000000))|((r[3]<l3)?UINT32_C(0x20000000):0u);
 const uint64_t l4=r[4];
 r[4]+=(uint64_t)(int64_t)(int16_t)UINT16_C(0xfa6c);
 c->xer=(c->xer&~UINT32_C(0x20000000))|((r[4]<l4)?UINT32_C(0x20000000):0u);
 c->lr=UINT32_C(0x003eef48);
 const int rc=ar_guest_call(c,UINT32_C(0x003e5a54));
 if(rc!=AR_OK)return rc;
 c->cia=UINT32_C(0x003eef48);return AR_TAIL;
}
typedef struct {uint32_t pc,n;uint64_t fnv;ar_ppu_fn fn;} m747_span;
static const m747_span spans[]={
 {0x003eef0cu,4u,UINT64_C(0xf310084da346e99f),ar_m747_native_003eef0c},
 {0x003eef20u,10u,UINT64_C(0xedbe0d6ca5406688),ar_m747_native_003eef20}
};
int ar_m747_register_owner(const uint8_t *elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 for(size_t i=0;i<sizeof(spans)/sizeof(spans[0]);i++){
  const m747_span*s=&spans[i];uint64_t h=UINT64_C(14695981039346656037);
  for(uint32_t j=0;j<s->n;j+=4u){
   uint32_t w[6]={0};
   const uint32_t n=s->n-j<4u?s->n-j:4u;
   if(ar_m712_exec_window(elf,len,s->pc+4u*j,w)!=AR_OK||
       w[4]<n||!(w[5]&1u))return AR_BAD_ARGS;
   for(uint32_t k=0;k<n;k++){
    const uint32_t v=w[k];
    if(ar_read32(s->pc+4u*(j+k))!=v||ar_last_error()!=AR_OK)return AR_BAD_ARGS;
    for(unsigned q=0;q<4u;q++){
     h^=(uint8_t)(v>>(24u-8u*q));h*=UINT64_C(1099511628211);
    }
   }
  }
  if(h!=s->fnv)return AR_BAD_ARGS;
 }
 for(size_t i=0;i<sizeof(spans)/sizeof(spans[0]);i++)
  if(ar_register(spans[i].pc,spans[i].fn)!=AR_OK)return AR_DUPLICATE;
 return AR_OK;
}
