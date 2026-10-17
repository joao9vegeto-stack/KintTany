#include "ppu_mmapper_internal.h"
int ar_sys_mmapper_allocate_memory(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 uint64_t n=c->gpr[3],f=c->gpr[4],out=c->gpr[5];
 if(!n||n>0x4000000u||mm_nb>=MM_MAX||mm_budget>0x10000000ull-n){
  c->gpr[3]=MM_NOMEM;return AR_OK;
 }
 if((f&0xf00u)!=0x400u || n%0x100000u){
  c->gpr[3]=MM_EALIGN;return AR_OK;
 }
 if(mm_check_output(out)!=AR_OK)return AR_MEM_FAULT;
 ar_write32(out,mm_next);if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 mm_blocks[mm_nb].id=mm_next++;mm_blocks[mm_nb].size=(uint32_t)n;
 mm_blocks[mm_nb].addr=0;mm_blocks[mm_nb++].data=NULL;
 mm_budget+=n;c->gpr[3]=0;return AR_OK;
}
