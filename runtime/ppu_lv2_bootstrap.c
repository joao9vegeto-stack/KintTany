/* M7.8: only OS service ABI, no PowerPC interpreter.
 * syscall 0x160 = sys_memory_get_user_memory_size:
 *  [r3] guest big-endian u32 total, u32 available.
 * sys_time_get_system_time (NID 0x8461E528): returns microseconds.
 *
 * Bootstrap budget: 256 MiB PS3 main memory, 224 MiB made available to
 * user processes in this compatibility profile (same tested M7.8 model).
 * These are PS3 guest model values, NOT measured iPhone physical RAM.
 * Future memory allocations must update available under one guest VM.
 */
#include "ppu_lv2_bootstrap.h"
#include <stdint.h>
#include <time.h>
enum { AR_USER_TOTAL=0x10000000u, AR_USER_AVAIL=0x0e000000u };
static unsigned memory_queries,time_queries;
void ar_lv2_bootstrap_reset(void){memory_queries=time_queries=0u;}
unsigned ar_lv2_user_memory_queries(void){return memory_queries;}
unsigned ar_lv2_time_queries(void){return time_queries;}
int ar_lv2_user_memory_size(ppu_context *cpu){
 if(!cpu)return AR_BAD_ARGS;
 uint64_t dest=cpu->gpr[3];
 if(!dest||(dest&3u)||dest>UINT32_MAX-7u)return AR_BAD_ARGS;
 (void)ar_read8(dest+7u);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 ar_write32(dest,AR_USER_TOTAL);
 ar_write32(dest+4u,AR_USER_AVAIL);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 cpu->gpr[3]=0; /* CELL_OK */
 ++memory_queries;
 return AR_OK;
}
int ar_lv2_system_time(ppu_context *cpu){
 if(!cpu)return AR_BAD_ARGS;
 struct timespec now={0};
 if(clock_gettime(CLOCK_MONOTONIC,&now)!=0 || now.tv_sec<0 ||
    now.tv_nsec<0 || now.tv_nsec>=1000000000L)return AR_HLE_FAILURE;
 const uint64_t microseconds=(uint64_t)now.tv_sec*UINT64_C(1000000)+
                              (uint64_t)now.tv_nsec/UINT64_C(1000);
 cpu->gpr[3]=microseconds;
 ++time_queries;
 return AR_OK;
}
