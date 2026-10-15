/* Context-aware generic PPC64 thread-local storage startup smoke. */
#ifndef AR_PPU_TLS_H
#define AR_PPU_TLS_H
#include "ppu_bridge.h"
int ar_tls_configure(uint32_t guest_region_begin,uint32_t guest_region_end);
int ar_sys_initialize_tls(ppu_context*);
#endif
