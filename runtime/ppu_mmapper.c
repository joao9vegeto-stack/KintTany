#include "ppu_mmapper_internal.h"
mm_range mm_ranges[MM_MAX];
mm_block mm_blocks[MM_MAX];
unsigned mm_nr,mm_nb;
uint32_t mm_next=0x08000000u;
uint64_t mm_budget;
int mm_check_output(uint64_t a){
 if(!a||(a&3u)||a>UINT32_MAX-3u)return AR_BAD_ARGS;
 (void)ar_read8(a+3u);return ar_last_error();
}
void ar_mmapper_reset(void){
 for(unsigned i=0;i<mm_nb;i++){
  if(mm_blocks[i].addr)ar_vm_external_unmap(mm_blocks[i].addr);
  free(mm_blocks[i].data);
 }
 memset(mm_blocks,0,sizeof(mm_blocks));
 memset(mm_ranges,0,sizeof(mm_ranges));
 mm_nb=mm_nr=0;mm_next=0x08000000u;mm_budget=0;
}
unsigned ar_mmapper_reservation_count(void){return mm_nr;}
unsigned ar_mmapper_object_count(void){return mm_nb;}
unsigned ar_mmapper_mapped_count(void){
 unsigned n=0;for(unsigned i=0;i<mm_nb;i++)if(mm_blocks[i].addr)n++;return n;
}
uint32_t ar_mmapper_reserved_address(unsigned i){return i<mm_nr?mm_ranges[i].addr:0;}
uint32_t ar_mmapper_reserved_size(unsigned i){return i<mm_nr?mm_ranges[i].size:0;}
