#ifndef AR_PPU_MMAPPER_H
#define AR_PPU_MMAPPER_H
#include "ppu_bridge.h"
#include <stdint.h>
void ar_mmapper_reset(void);
int ar_sys_mmapper_allocate_address(ppu_context*);
int ar_sys_mmapper_allocate_memory(ppu_context*);
int ar_sys_mmapper_map_memory(ppu_context*);
int ar_sys_mmapper_unmap_memory(ppu_context*);
int ar_sys_mmapper_free_memory(ppu_context*);
unsigned ar_mmapper_reservation_count(void);
unsigned ar_mmapper_object_count(void);
unsigned ar_mmapper_mapped_count(void);
uint32_t ar_mmapper_reserved_address(unsigned);
uint32_t ar_mmapper_reserved_size(unsigned);
#endif
