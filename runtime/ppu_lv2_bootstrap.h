/* Generic PS3 Cell LV2 bootstrap handlers for authentic signed AOT. */
#ifndef AR_LV2_BOOTSTRAP_H
#define AR_LV2_BOOTSTRAP_H
#include "ppu_bridge.h"
void ar_lv2_bootstrap_reset(void);
int ar_lv2_user_memory_size(ppu_context *cpu); /* syscall 0x160 */
int ar_lv2_system_time(ppu_context *cpu);      /* NID 0x8461E528 */
unsigned ar_lv2_user_memory_queries(void);
unsigned ar_lv2_time_queries(void);
#endif
