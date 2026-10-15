/* Pure synthetic guest import registration smoke. */
#include <stdio.h>
#include "ppu_bridge.h"
extern int ar_register_guest_import_manifest(void);
extern int ppu_f_00010200(ppu_context *);
static int example_ctx_hle(ppu_context* c) {
 c->gpr[3]=ar_read32(c->gpr[3]);c->gpr[2]=0xdead;return 0;
}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL import manifest %d: %s\n",__LINE__,#x);return 4;}}while(0)
int main(void) {
 CHECK(ar_bridge_init(256*1024)==AR_OK);
 CHECK(ar_register(0x10200,ppu_f_00010200)==AR_OK);
 CHECK(ar_register_guest_import_manifest()==AR_OK);
 CHECK(ar_register_guest_import_manifest()==AR_DUPLICATE);
 CHECK(ar_last_missing_nid()==0);
 ar_write32(0x800,0x12345678);
 ppu_context c={0};c.lr=0x1200;c.gpr[2]=0x20080;
 CHECK(ar_run(&c,0x10200,50)==AR_MISSING_HLE);
 CHECK(ar_last_missing_nid()==0x11223344);
 CHECK(ar_bind_hle(0x11223344,example_ctx_hle)==AR_OK);
 c.lr=0x1200;c.gpr[2]=0x20080;
 CHECK(ar_run(&c,0x10200,50)==AR_OK);
 CHECK(c.gpr[3]==0x12345678&&c.gpr[2]==0x20080&&c.lr==0x1200);
 ar_bridge_shutdown();
 puts("PASS: manifest-generated stub/NID, strict missing import, canonical context ABI");
 return 0;
}
