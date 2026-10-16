#include <stdint.h>
#include <stdio.h>
uint64_t ar_ppu_timebase_ticks(void);
int main(void){
    uint64_t a=ar_ppu_timebase_ticks(),b=ar_ppu_timebase_ticks();
    if(!a || b<a)return 1;
    puts("M7.10 guest PPU timebase native host PASS");
    return 0;
}
