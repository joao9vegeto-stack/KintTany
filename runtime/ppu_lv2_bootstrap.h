/* Generic PS3 Cell LV2 service handlers. */
#ifndef AR_LV2_BOOTSTRAP_H
#define AR_LV2_BOOTSTRAP_H
#include "ppu_bridge.h"
void ar_lv2_bootstrap_reset(void);
int ar_lv2_user_memory_size(ppu_context *cpu);
int ar_lv2_system_time(ppu_context *cpu);
/* LV2 syscall 147 (0x093): 64-bit timebase frequency in guest r3. */
int ar_lv2_timebase_frequency(ppu_context *cpu);
/* LV2 syscall #144: guest BE s32 standard timezone + DST shift (minutes). */
int ar_lv2_timezone(ppu_context *cpu);
int ar_lv2_timezone_values(ppu_context *cpu,int32_t standard_east_minutes,
                            int32_t dst_minutes);
unsigned ar_lv2_timezone_queries(void);
int ar_lv2_current_time(ppu_context *cpu);
int ar_lv2_current_time_values(ppu_context *cpu,uint64_t sec,uint64_t nsec);
unsigned ar_lv2_current_time_queries(void);
unsigned ar_lv2_timebase_queries(void);
int ar_lv2_thread_get_id(ppu_context *cpu);
unsigned ar_lv2_user_memory_queries(void);
unsigned ar_lv2_time_queries(void);
#endif
