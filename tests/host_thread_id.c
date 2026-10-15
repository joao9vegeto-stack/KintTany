#include <stdio.h>
#include "ppu_thread_services.h"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"M36 FAIL %d %s\n",__LINE__,#x);return 3;}}while(0)
int main(void) {
 CHECK(ar_bridge_init(8192)==AR_OK);
 ppu_context a={0},b={0};a.thread_id=1;b.thread_id=7;
 a.gpr[3]=0x800;b.gpr[3]=0x810;
 CHECK(ar_sys_ppu_thread_get_id(&a)==AR_OK && a.gpr[3]==0);
 CHECK(ar_sys_ppu_thread_get_id(&b)==AR_OK && b.gpr[3]==0);
 CHECK(ar_read64(0x800)==1 && ar_read64(0x810)==7);
 b.gpr[3]=8190;
 CHECK(ar_sys_ppu_thread_get_id(&b)==AR_MEM_FAULT);
 b.gpr[3]=0x900;b.thread_id=0;
 CHECK(ar_sys_ppu_thread_get_id(&b)==AR_BAD_ARGS);
 ar_bridge_shutdown();
 puts("PASS: sys_ppu_thread_get_id reports calling thread and bounds-checks BE output");
 return 0;
}
