/* Address reservation does not allocate physical guest pages. */
#include "ppu_mmapper_internal.h"
int ar_sys_mmapper_allocate_address(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t size=c->gpr[3],flags=c->gpr[4],align=c->gpr[5],dst=c->gpr[6];
 if(!size||size%MM_ALIGN){c->gpr[3]=MM_EALIGN;return AR_OK;}
 if(size>UINT32_MAX||mm_nr==MM_MAX){c->gpr[3]=MM_NOMEM;return AR_OK;}
 if(!align)align=MM_ALIGN;
 if(align!=0x10000000u&&align!=0x20000000u&&align!=0x40000000u&&align!=0x80000000u){
  c->gpr[3]=MM_EALIGN;return AR_OK;
 }
 if((flags&~UINT64_C(0xf00))||(flags&0xf00u)!=0x400u){
  c->gpr[3]=MM_INVAL;return AR_OK;
 }
 if(mm_check_output(dst)!=AR_OK)return AR_MEM_FAULT;
 uint32_t chosen=0;
 for(uint64_t a=0x20000000ull;a+size<=0xb0000000ull;a+=MM_ALIGN){
  if(a%align)continue;
  int overlap=0;
  for(unsigned i=0;i<mm_nr;i++)
   if(a<(uint64_t)mm_ranges[i].addr+mm_ranges[i].size &&
      (uint64_t)mm_ranges[i].addr<a+size)overlap=1;
  if(!overlap){chosen=(uint32_t)a;break;}
 }
 if(!chosen){c->gpr[3]=MM_NOMEM;return AR_OK;}
 ar_write32(dst,chosen);if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 mm_ranges[mm_nr].addr=chosen;mm_ranges[mm_nr++].size=(uint32_t)size;
 c->gpr[3]=0;return AR_OK;
}
