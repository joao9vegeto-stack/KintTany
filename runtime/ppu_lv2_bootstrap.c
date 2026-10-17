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
#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif
#include "ppu_lv2_bootstrap.h"
#include <stdint.h>
#include <time.h>
enum { AR_USER_TOTAL=0x10000000u, AR_USER_AVAIL=0x0e000000u };
static unsigned memory_queries,time_queries,timebase_queries,current_time_queries,timezone_queries;
void ar_lv2_bootstrap_reset(void){memory_queries=time_queries=timebase_queries=current_time_queries=timezone_queries=0u;}
/* M7.33: use the identical dispatcher registration in iOS and host tests. */
int ar_lv2_bind_bootstrap_syscalls(void){
 const struct {uint32_t number;ar_hle_fn fn;} services[]={
  {UINT32_C(0x160),ar_lv2_user_memory_size},
  {UINT32_C(147),ar_lv2_timebase_frequency},
  {UINT32_C(145),ar_lv2_current_time},
  {UINT32_C(144),ar_lv2_timezone}
 };
 for(size_t i=0;i<sizeof(services)/sizeof(services[0]);i++){
    const int rc=ar_bind_syscall(services[i].number,services[i].fn);
    if(rc!=AR_OK)return rc;
 }
 return AR_OK;
}
unsigned ar_lv2_user_memory_queries(void){return memory_queries;}
unsigned ar_lv2_time_queries(void){return time_queries;}
unsigned ar_lv2_timebase_queries(void){return timebase_queries;}
unsigned ar_lv2_current_time_queries(void){return current_time_queries;}
unsigned ar_lv2_timezone_queries(void){return timezone_queries;}
/* Hardware-compatible PS3 Cell 79.8 MHz timebase, NOT iPhone CPU clock.
 * Syscall returns frequency as u64 directly in guest r3 (not CELL_OK).
 * Keep guest tick/frequency clock domains consistent in future runtimes. */
int ar_lv2_timebase_frequency(ppu_context *cpu){
 if(!cpu)return AR_BAD_ARGS;
 cpu->gpr[3]=UINT64_C(79800000);
 ++timebase_queries;
 return AR_OK;
}
/* PS3 LV2 145: UNIX epoch seconds/nanoseconds in two BE guest 64-bit
 * addresses r3 and r4. Refuse invalid pointer before modifying either. */
int ar_lv2_current_time_values(ppu_context *cpu,uint64_t sec,uint64_t nsec){
 if(!cpu||nsec>=UINT64_C(1000000000))return AR_BAD_ARGS;
 const uint64_t psec=cpu->gpr[3],pnsec=cpu->gpr[4];
 if(!psec||!pnsec||(psec&7u)||(pnsec&7u)||
    psec>UINT32_MAX-7u||pnsec>UINT32_MAX-7u||
    (psec<=pnsec+7u && pnsec<=psec+7u))return AR_BAD_ARGS;
 uint8_t probe[8];
 if(ar_vm_read_bytes(psec,probe,8)!=AR_OK ||
    ar_vm_read_bytes(pnsec,probe,8)!=AR_OK)return AR_MEM_FAULT;
 uint8_t s[8],n[8];
 for(unsigned i=0;i<8;i++){
    s[7u-i]=(uint8_t)(sec>>(i*8u));
    n[7u-i]=(uint8_t)(nsec>>(i*8u));
 }
 if(ar_vm_load(psec,s,8)!=AR_OK ||
    ar_vm_load(pnsec,n,8)!=AR_OK)return AR_MEM_FAULT;
 cpu->gpr[3]=0; /* CELL_OK only when both buffers were written */
 ++current_time_queries;
 return AR_OK;
}
int ar_lv2_current_time(ppu_context *cpu){
 if(!cpu)return AR_BAD_ARGS;
 struct timespec now={0};
 if(clock_gettime(CLOCK_REALTIME,&now)!=0||now.tv_sec<0||
    now.tv_nsec<0||now.tv_nsec>=1000000000L)return AR_LV2_FAILURE;
 return ar_lv2_current_time_values(cpu,(uint64_t)now.tv_sec,
                                   (uint64_t)now.tv_nsec);
}
/* syscall 144: sys_time_get_timezone(s32* tz_minutes_east,
 * s32* summertime_minutes). These are *two 32-bit guest pointers*, unlike
 * syscall 145's seconds/nanoseconds 64-bit pointers.
 * timezone is the standard (non-DST) UTC offset in minutes east of GMT,
 * summertime is the additional offset for current DST.
 * No hardcoded region/UTC override; honor device's timezone.
 * Test-injectable values verify BE encoding and pointer atomic validation.
 */
int ar_lv2_timezone_values(ppu_context *cpu,int32_t minutes_east,
                           int32_t summertime){
 if(!cpu)return AR_BAD_ARGS;
 if(minutes_east<-1440||minutes_east>1440||
    summertime<0||summertime>180)return AR_BAD_ARGS;
 const uint64_t pa=cpu->gpr[3],pb=cpu->gpr[4];
 if(!pa||!pb||(pa&3u)||(pb&3u)||
    pa>UINT32_MAX-3u||pb>UINT32_MAX-3u||
    (pa<=pb+3u&&pb<=pa+3u))return AR_BAD_ARGS;
 uint8_t probe[4];
 if(ar_vm_read_bytes(pa,probe,4)!=AR_OK||
    ar_vm_read_bytes(pb,probe,4)!=AR_OK)return AR_MEM_FAULT;
 uint8_t aa[4],bb[4];
 uint32_t a=(uint32_t)minutes_east,b=(uint32_t)summertime;
 for(unsigned i=0;i<4;i++){
    aa[3-i]=(uint8_t)(a>>(i*8u));
    bb[3-i]=(uint8_t)(b>>(i*8u));
 }
 if(ar_vm_load(pa,aa,4)!=AR_OK||
    ar_vm_load(pb,bb,4)!=AR_OK)return AR_MEM_FAULT;
 cpu->gpr[3]=0u;
 timezone_queries++;
 return AR_OK;
}
int ar_lv2_timezone(ppu_context *cpu){
 if(!cpu)return AR_BAD_ARGS;
 const time_t now=time(NULL);
 if(now==(time_t)-1)return AR_LV2_FAILURE;
 tzset();
 struct tm current;
 if(!localtime_r(&now,&current) || current.tm_isdst<0)
    return AR_LV2_FAILURE;
 const long curr_off=(long)current.tm_gmtoff;
 long base_off=curr_off;
 if(current.tm_isdst>0){
    /* Pick the standard-time offset from a summer/winter pair. This
     * preserves regions with non-hour DST shifts (e.g. +30 minutes). */
    struct tm candidate;
    struct tm probe=current;
    probe.tm_mon=0;probe.tm_mday=15;probe.tm_hour=12;
    probe.tm_min=0;probe.tm_sec=0;probe.tm_isdst=-1;
    time_t probe_time=mktime(&probe);
    if(probe_time!=(time_t)-1 &&
       localtime_r(&probe_time,&candidate) && candidate.tm_isdst==0)
       base_off=(long)candidate.tm_gmtoff;
    else{
       probe=current;probe.tm_mon=6;probe.tm_mday=15;
       probe.tm_hour=12;probe.tm_min=0;probe.tm_sec=0;probe.tm_isdst=-1;
       probe_time=mktime(&probe);
       if(probe_time==(time_t)-1||
          !localtime_r(&probe_time,&candidate)||
          candidate.tm_isdst!=0)return AR_LV2_FAILURE;
       base_off=(long)candidate.tm_gmtoff;
    }
 }
 if(curr_off%60L || base_off%60L ||
    curr_off/60L>INT32_MAX || curr_off/60L<INT32_MIN ||
    base_off/60L>INT32_MAX || base_off/60L<INT32_MIN ||
    (curr_off-base_off)/60L>INT32_MAX)return AR_LV2_FAILURE;
 return ar_lv2_timezone_values(cpu,(int32_t)(base_off/60L),
                               (int32_t)((curr_off-base_off)/60L));
}
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

/* M7.9 PS3 sysPrxForUser: sys_ppu_thread_get_id, NID 0x350D454E.
 * The sole registered bootstrap PPU thread is created by ELF stage.
 * Return the authenticated thread id through the guest BE uint64 pointer. */
int ar_lv2_thread_get_id(ppu_context *cpu){
 if(!cpu || !cpu->thread_id)return AR_BAD_ARGS;
 const uint64_t ptr=cpu->gpr[3];
 if(!ptr||(ptr&7u)||ptr>UINT32_MAX-7u)return AR_BAD_ARGS;
 (void)ar_read8(ptr+7u);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 ar_write64(ptr,cpu->thread_id);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 cpu->gpr[3]=0u;
 return AR_OK;
}
