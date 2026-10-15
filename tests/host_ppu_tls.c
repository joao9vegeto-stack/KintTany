#include <stdio.h>
#include "ppu_tls.h"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"TLS FAIL line %d %s\n",__LINE__,#x);return 2;}}while(0)
int main(void){
 CHECK(ar_bridge_init(16u*1024u*1024u)==AR_OK);
 CHECK(ar_tls_configure(0xc00000,0xe00000)==AR_OK);
 ar_write32(0x3000,0x12345678);
 ppu_context c={0};c.gpr[3]=1;c.gpr[4]=0x3000;c.gpr[5]=4;c.gpr[6]=0x180;
 CHECK(ar_sys_initialize_tls(&c)==AR_OK);
 CHECK(c.gpr[13]==0xc07000&&c.gpr[3]==0);
 CHECK(ar_read32(0xc00000)==0x12345678);
 CHECK(ar_read32(0xc00004)==0);
 c.gpr[5]=0x181;
 CHECK(ar_sys_initialize_tls(&c)==AR_BAD_ARGS);
 CHECK(ar_tls_configure(0xe00000,0xe00100)==AR_BAD_ARGS);
 ar_bridge_shutdown();
 puts("PASS: sys_initialize_tls copies actual bytes, BSS zero, sets r13, checks bounds");
 return 0;
}
