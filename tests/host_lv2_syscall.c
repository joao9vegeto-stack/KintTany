#include <stdio.h>
#include "lv2_smoke.h"
extern int ppu_f_00018000(ppu_context*);
#define CHECK(x) do{if(!(x)){fprintf(stderr,"LV2 FAIL %d: %s\n",__LINE__,#x);return 3;}}while(0)
int main(void){
 CHECK(ar_bridge_init(256*1024)==AR_OK);
 CHECK(ar_register(0x18000,ppu_f_00018000)==AR_OK);
 ppu_context c={0};c.lr=0x1234;
 CHECK(ar_run(&c,0x18000,12)==AR_MISSING_LV2);
 CHECK(ar_last_missing_syscall()==352);
 CHECK(ar_bind_syscall(352,ar_lv2_memory_get_user_size)==AR_OK);
 CHECK(ar_bind_syscall(352,ar_lv2_memory_get_user_size)==AR_DUPLICATE);
 c.lr=0x1234;
 CHECK(ar_run(&c,0x18000,12)==AR_OK);
 CHECK(ar_read32(0x1000)==0x10000000u);
 CHECK(ar_read32(0x1004)==0x0c000000u);
 CHECK(c.gpr[3]==0&&ar_last_missing_syscall()==0);
 ar_bridge_shutdown();
 puts("PASS: PPU sc uses r11 LV2 number; unknown fails; syscall352 writes big-endian outputs");
 return 0;
}
