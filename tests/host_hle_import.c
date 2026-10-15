/* No game assets: synthetic ABI and missing-HLE behavior proof. */
#include <stdint.h>
#include <stdio.h>
#include "ppu_bridge.h"
extern int ppu_f_00010200(ppu_context*);
static int read_guest_word(ppu_context*c) {
 c->gpr[3]=ar_read32(c->gpr[3]);
 c->gpr[2]=0xdead;
 return 0;
}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"HLE FAIL line %d: %s\n",__LINE__,#x);return 2;}}while(0)
int main(void){
 CHECK(ar_bridge_init(256*1024)==AR_OK);
 CHECK(ar_register(0x10200,ppu_f_00010200)==AR_OK);
 CHECK(ar_bind_import(0x10220,0x11223344)==AR_OK);
 CHECK(ar_bind_import(0x10220,0x11223344)==AR_DUPLICATE);
 ar_write32(0x800,0xabcdeeff);
 ppu_context c={0};c.lr=0x1234;c.gpr[2]=0x20080;
 CHECK(ar_run(&c,0x10200,20)==AR_MISSING_HLE);
 CHECK(ar_last_missing_nid()==0x11223344);
 CHECK(ar_bind_hle(0x11223344,read_guest_word)==AR_OK);
 CHECK(ar_bind_hle(0x11223344,read_guest_word)==AR_DUPLICATE);
 c.lr=0x1234;c.gpr[2]=0x20080;
 CHECK(ar_run(&c,0x10200,20)==AR_OK);
 CHECK(c.gpr[3]==0xabcdeeff);
 CHECK(c.gpr[2]==0x20080&&c.lr==0x1234);
 CHECK(ar_last_missing_nid()==0);
 ar_bridge_shutdown();
 puts("PASS: import stub NID match; missing HLE fails; guest big-endian pointer and TOC restore");
 return 0;
}
