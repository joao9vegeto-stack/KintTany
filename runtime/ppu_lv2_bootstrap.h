/* Generic PS3 Cell LV2 service handlers. */
#ifndef AR_LV2_BOOTSTRAP_H
#define AR_LV2_BOOTSTRAP_H
#include "ppu_bridge.h"
void ar_lv2_bootstrap_reset(void);
int ar_lv2_user_memory_size(ppu_context *cpu);
int ar_lv2_system_time(ppu_context *cpu);
int ar_lv2_thread_get_id(ppu_context *cpu);
unsigned ar_lv2_user_memory_queries(void);
unsigned ar_lv2_time_queries(void);
#endif
