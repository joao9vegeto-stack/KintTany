/* Cell/PPU time base for precompiled native ARM64 game functions.
 * 79.8 MHz guest clock from host monotonic time; no PPC interpreter. */
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#include <stdint.h>
#include <time.h>
uint64_t ar_ppu_timebase_ticks(void){
    struct timespec now={0};
    if(clock_gettime(CLOCK_MONOTONIC,&now)!=0 || now.tv_sec<0 ||
       now.tv_nsec<0 || now.tv_nsec>=1000000000L)return 0;
    return (uint64_t)now.tv_sec*UINT64_C(79800000)+
           (uint64_t)now.tv_nsec*UINT64_C(79800000)/UINT64_C(1000000000);
}
