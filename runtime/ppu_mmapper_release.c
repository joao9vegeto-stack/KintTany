#include "ppu_mmapper_internal.h"
int ar_sys_mmapper_unmap_memory(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t addr=c->gpr[3],out=c->gpr[4];
 if(mm_check_output(out)!=AR_OK)return AR_MEM_FAULT;
 for(unsigned i=0;i<mm_nb;i++)if(addr && mm_blocks[i].addr==addr){
  if(ar_vm_external_unmap((uint32_t)addr)!=AR_OK)return AR_MEM_FAULT;
  mm_blocks[i].addr=0;
  ar_write32(out,mm_blocks[i].id);if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
  c->gpr[3]=0;return AR_OK;
 }
 c->gpr[3]=MM_INVAL;return AR_OK;
}
int ar_sys_mmapper_free_memory(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 for(unsigned i=0;i<mm_nb;i++)if(mm_blocks[i].id==c->gpr[3]){
  if(mm_blocks[i].addr){c->gpr[3]=MM_BUSY;return AR_OK;}
  free(mm_blocks[i].data);mm_budget-=mm_blocks[i].size;
  mm_blocks[i]=mm_blocks[--mm_nb];
  memset(&mm_blocks[mm_nb],0,sizeof(mm_blocks[0]));
  c->gpr[3]=0;return AR_OK;
 }
 c->gpr[3]=MM_INVAL;return AR_OK;
}
