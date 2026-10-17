#include "ppu_mmapper_internal.h"
/* Allocates actual guest RAM on map, rejects overlap and missing reservation. */
int ar_sys_mmapper_map_memory(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 uint64_t addr=c->gpr[3],id=c->gpr[4],flags=c->gpr[5];
 if(addr>UINT32_MAX||(addr&0xfffffu)||(flags&~UINT64_C(0x40000))){
  c->gpr[3]=MM_INVAL;return AR_OK;
 }
 for(unsigned i=0;i<mm_nb;i++)if(mm_blocks[i].id==id){
  if(mm_blocks[i].addr){c->gpr[3]=MM_BUSY;return AR_OK;}
  int valid=0;
  for(unsigned j=0;j<mm_nr;j++)
   if(addr>=mm_ranges[j].addr &&
      addr+mm_blocks[i].size<=(uint64_t)mm_ranges[j].addr+mm_ranges[j].size)valid=1;
  if(!valid){c->gpr[3]=MM_INVAL;return AR_OK;}
  if(!mm_blocks[i].data){
   mm_blocks[i].data=calloc(mm_blocks[i].size,1u);
   if(!mm_blocks[i].data){c->gpr[3]=MM_NOMEM;return AR_OK;}
  }
  if(ar_vm_external_map((uint32_t)addr,mm_blocks[i].data,mm_blocks[i].size)!=AR_OK){
   c->gpr[3]=MM_BUSY;return AR_OK;
  }
  mm_blocks[i].addr=(uint32_t)addr;c->gpr[3]=0;return AR_OK;
 }
 c->gpr[3]=MM_INVAL;return AR_OK;
}
