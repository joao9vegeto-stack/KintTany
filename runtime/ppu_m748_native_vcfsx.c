/* M7.48: 31 real GOWA.ELF PPC instructions native C -> Apple ARM64.
 * Covers the exact iPhone-observed VMX vcfsx function and hot suffix.
 * Owner executable + guest-VM matching and pre-existing whole-file
 * SHA gate required. No JIT, no RPCS3 and no game files bundled. */
#include <stddef.h>
#include <stdint.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
static int vmx_store(ppu_context*c,unsigned vr,uint64_t ea){
 return ar_vmx_guest_store(c,vr,ea,0u);
}
static int vmx_load(ppu_context*c,unsigned vr,uint64_t ea){
 return ar_vmx_guest_load(c,vr,ea,0u);
}
static int suffix(ppu_context*c){
 uint64_t *r=c->gpr;
 /* 003DDF54 vcfsx v2,v2,0; conversion is exact round-to-nearest-even. */
 ar_vmx_vcfsx(c,2u,2u,0u);
 r[6]=(uint64_t)(int64_t)(int16_t)UINT16_C(0x80e0);
 r[10]=UINT64_C(0x009d0000);
 r[11]=(uint64_t)(int64_t)(int16_t)UINT16_C(0x80f0);
 r[12]=64u;
 if(vmx_store(c,2u,r[4]+r[8])!=AR_OK)return AR_MEM_FAULT;
 if(vmx_load(c,2u,r[7]+r[3])!=AR_OK)return AR_MEM_FAULT;
 ar_vmx_vcfsx(c,2u,2u,0u);
 r[4]=UINT64_C(0x009d0000);
 r[7]=(uint64_t)(int64_t)(int16_t)UINT16_C(0x8100);
 if(vmx_store(c,2u,r[6]+r[5])!=AR_OK)return AR_MEM_FAULT;
 if(vmx_load(c,2u,r[9]+r[3])!=AR_OK)return AR_MEM_FAULT;
 ar_vmx_vcfsx(c,2u,2u,0u);
 if(vmx_store(c,2u,r[11]+r[10])!=AR_OK)return AR_MEM_FAULT;
 if(vmx_load(c,2u,r[12]+r[3])!=AR_OK)return AR_MEM_FAULT;
 ar_vmx_vcfsx(c,2u,2u,0u);
 if(vmx_store(c,2u,r[7]+r[4])!=AR_OK)return AR_MEM_FAULT;
 c->cia=(uint32_t)c->lr; /* original PPC BLR */
 return AR_TAIL;
}
int ar_m748_native_003ddf20(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 r[3]=UINT64_C(0x003e0000);
 r[4]=UINT64_C(0x009c0000);
 r[3]+=(uint64_t)(int64_t)(int16_t)UINT16_C(0xded0);
 r[5]=UINT64_C(0x78b0);
 r[6]=16u;
 r[8]=UINT64_C(0x009d0000);
 r[7]=32u;
 if(vmx_load(c,2u,r[3])!=AR_OK)return AR_MEM_FAULT;
 if(vmx_store(c,2u,r[5]+r[4])!=AR_OK)return AR_MEM_FAULT;
 r[9]=48u;
 if(vmx_load(c,2u,r[6]+r[3])!=AR_OK)return AR_MEM_FAULT;
 r[4]=(uint64_t)(int64_t)(int16_t)UINT16_C(0x80d0);
 r[5]=UINT64_C(0x009d0000);
 return suffix(c);
}
int ar_m748_native_003ddf54(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 return suffix(c);
}
typedef struct {uint32_t pc,n;uint64_t fnv;ar_ppu_fn fn;} m748_span;
static const m748_span spans[]={
 {UINT32_C(0x003ddf20),31u,UINT64_C(0xfb0acf25e4d1ffbe),ar_m748_native_003ddf20},
 {UINT32_C(0x003ddf54),18u,UINT64_C(0x28089fab4a53d0b1),ar_m748_native_003ddf54}
};
int ar_m748_register_owner(const uint8_t*elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 /* Both candidate entrypoints are verified BEFORE any is installed. */
 for(unsigned x=0;x<sizeof(spans)/sizeof(spans[0]);x++){
  const m748_span*s=&spans[x];
  uint64_t h=UINT64_C(14695981039346656037);
  for(uint32_t i=0;i<s->n;i+=4u){
   uint32_t words[6]={0};
   const uint32_t n=(s->n-i<4u)?s->n-i:4u;
   if(ar_m712_exec_window(elf,len,s->pc+i*4u,words)!=AR_OK ||
      words[4]<n || !(words[5]&1u))return AR_BAD_ARGS;
   for(uint32_t j=0;j<n;j++){
    const uint32_t v=words[j],addr=s->pc+4u*(i+j);
    if(ar_read32(addr)!=v||ar_last_error()!=AR_OK)return AR_BAD_ARGS;
    for(unsigned q=0;q<4u;q++){
      h^=(uint8_t)(v>>(24u-8u*q));
      h*=UINT64_C(1099511628211);
    }
   }
  }
  if(h!=s->fnv)return AR_BAD_ARGS;
 }
 for(unsigned i=0;i<sizeof(spans)/sizeof(spans[0]);i++)
    if(ar_register(spans[i].pc,spans[i].fn)!=AR_OK)return AR_DUPLICATE;
 return AR_OK;
}
