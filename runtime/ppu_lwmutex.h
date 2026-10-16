/* M7.7: PS3 sysPrxForUser lightweight mutex ABI; bounded single-process
 * bootstrap. This module is general PS3 ABI code, never game-derived. */
#ifndef AR_LWMUTEX_H
#define AR_LWMUTEX_H
#include "ppu_bridge.h"
void ar_lwmutex_reset(void);
int ar_sys_lwmutex_create(ppu_context *cpu);
unsigned ar_lwmutex_created_count(void);
#endif
