/* M7.50 native PPC64->AppleARM64 path at real M7.49 iPhone frontier.
 * Owner executable text + loaded guest VM authenticated before install.
 * 0x003B1D78..0x003B1DC0 (19 PPC) and 0x003B1DC4..0x003B1DD4 (5 PPC).
 * No JIT, no RPCS3, no shortcut around guest calls/filesystem. */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
#include "ppu_fp_scalar.h"
#include "ppu_vmx_cell.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define CA UINT32_C(0x20000000)
static uint64_t addic(ppu_context*c,uint64_t a,int32_t v){
 const uint64_t b=(uint64_t)(int64_t)v,z=a+b;
 c->xer=(c->xer&~CA)|(z<a?CA:0u);return z;
}
static int st8(uint64_t ea,uint64_t v){
 ar_write8(ea,(uint8_t)v);
 return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;
}
static int st32(uint64_t ea,uint64_t v){
 ar_write32(ea,(uint32_t)v);
 return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;
}
static int stvx(ppu_context*c,unsigned v,uint64_t a,uint64_t b){
 return ar_vmx_guest_store(c,v,a+b,0u);
}
int ar_m750_native_003b1d78(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t *r=c->gpr;
 int rc=ar_fp_fsubs(c,1u,1u,31u); /* 0xEC21F828 fsubs f1,f1,f31 */
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b1d78);return rc;}
 rc=ar_fp_store(c,1u,r[31]+UINT64_C(1168),1); /* STFS */
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b1d7c);return rc;}
 /* All 12 STVX preserve guest 128-bit vector order and alignment. */
 const unsigned vr[]={9u,8u,10u,11u,12u,13u,0u,1u,2u,3u,5u,4u};
 const unsigned ra[]={5u,6u,7u,0u,5u,6u,7u,0u,5u,6u,7u,0u};
 const unsigned rb[]={9u,9u,9u,9u,10u,10u,10u,10u,4u,4u,4u,4u};
 for(unsigned i=0;i<12u;i++){
   /* RA zero means literal 0, not GPR0. */
   rc=stvx(c,vr[i],ra[i]?r[ra[i]]:0u,r[rb[i]]);
   if(rc!=AR_OK){c->cia=UINT32_C(0x003b1d80)+4u*i;return rc;}
 }
 if(st32(r[31]+UINT64_C(1156),r[30])!=AR_OK){
   c->cia=UINT32_C(0x003b1db0);return AR_MEM_FAULT;
 }
 if(st32(r[31]+UINT64_C(1184),r[8])!=AR_OK){
   c->cia=UINT32_C(0x003b1db4);return AR_MEM_FAULT;
 }
 if(st32(r[31]+UINT64_C(1160),r[28])!=AR_OK){
   c->cia=UINT32_C(0x003b1db8);return AR_MEM_FAULT;
 }
 if(st8(r[31]+UINT64_C(1188),r[12])!=AR_OK){
   c->cia=UINT32_C(0x003b1dbc);return AR_MEM_FAULT;
 }
 if(st32(r[31]+UINT64_C(1284),r[30])!=AR_OK){
   c->cia=UINT32_C(0x003b1dc0);return AR_MEM_FAULT;
 }
 c->cia=UINT32_C(0x003b1dc4);
 return AR_TAIL; /* dispatch authentic next native loop entry */
}
int ar_m750_native_003b1dc4(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t *r=c->gpr;
 for(unsigned attempts=0;attempts<16384u;attempts++){
   /* addic r4,r3,1204 ; addic r3,r3,4 */
   r[4]=addic(c,r[3],1204);
   r[3]=addic(c,r[3],4);
   r[4]=(uint32_t)r[4]; /* clrldi r4,r4,32 */
   if(st32(r[4],r[30])!=AR_OK){
     c->cia=UINT32_C(0x003b1dd0);return AR_MEM_FAULT;
   }
   c->ctr--; /* original bdnz 0x003b1dc4, 64-bit CTR */
   if(c->ctr==0u){
     c->cia=UINT32_C(0x003b1dd8);return AR_TAIL;
   }
 }
 c->cia=UINT32_C(0x003b1dc4);return AR_PPC_LIMIT;
}
typedef struct{uint32_t pc,n;uint64_t fnv;ar_ppu_fn fn;} owner_span;
static const owner_span spans[]={
 {UINT32_C(0x003b1d78),19u,UINT64_C(0x52959d588494ed68),ar_m750_native_003b1d78},
 {UINT32_C(0x003b1dc4),5u,UINT64_C(0x7f23904155db70b7),ar_m750_native_003b1dc4}
};
int ar_m750_register_owner(const uint8_t *elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 for(unsigned i=0;i<sizeof(spans)/sizeof(spans[0]);i++){
  const owner_span*s=&spans[i];
  uint64_t h=UINT64_C(14695981039346656037);
  for(uint32_t k=0;k<s->n;k+=4u){
   uint32_t words[6]={0};
   const uint32_t n=(s->n-k<4u)?s->n-k:4u;
   if(ar_m712_exec_window(elf,len,s->pc+4u*k,words)!=AR_OK ||
      words[4]<n || !(words[5]&1u))return AR_BAD_ARGS;
   for(uint32_t j=0;j<n;j++){
    const uint32_t v=words[j],pc=s->pc+4u*(k+j);
    if(ar_read32(pc)!=v||ar_last_error()!=AR_OK)return AR_BAD_ARGS;
    for(unsigned a=0;a<4u;a++){
     h^=(uint8_t)(v>>(24u-8u*a));
     h*=UINT64_C(1099511628211);
    }
   }
  }
  if(h!=s->fnv)return AR_BAD_ARGS;
 }
 for(unsigned i=0;i<sizeof(spans)/sizeof(spans[0]);i++){
   if(ar_register(spans[i].pc,spans[i].fn)!=AR_OK)return AR_DUPLICATE;
 }
 return AR_OK;
}
