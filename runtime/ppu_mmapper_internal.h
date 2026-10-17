#ifndef AR_MM_INTERNAL_H
#define AR_MM_INTERNAL_H
#include "ppu_mmapper.h"
#include <stdlib.h>
#include <string.h>
enum {MM_MAX=512,MM_ALIGN=0x10000000u,MM_NOMEM=0x80010004u,
 MM_EALIGN=0x80010010u,MM_INVAL=0x80010002u,MM_BUSY=0x80010014u};
typedef struct {uint32_t addr,size;} mm_range;
typedef struct {uint32_t id,size,addr;uint8_t* data;} mm_block;
extern mm_range mm_ranges[MM_MAX];
extern mm_block mm_blocks[MM_MAX];
extern unsigned mm_nr,mm_nb;
extern uint32_t mm_next;
extern uint64_t mm_budget;
int mm_check_output(uint64_t);
#endif
