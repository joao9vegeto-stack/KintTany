/* Synthetic PPU host smoke, compile also against PINNED actual upstream. */
#include <stddef.h>
#include <stdio.h>
#include "ppu_bridge.h"
_Static_assert(offsetof(ppu_context,gpr)==0,"GPR ABI");
_Static_assert(offsetof(ppu_context,fpr)==256,"FPR ABI");
_Static_assert(offsetof(ppu_context,vr)==512,"VMX ABI");
_Static_assert(offsetof(ppu_context,cr)==1024,"CR ABI");
_Static_assert(offsetof(ppu_context,lr)==1032,"LR ABI");
_Static_assert(offsetof(ppu_context,ctr)==1040,"CTR ABI");
_Static_assert(offsetof(ppu_context,xer)==1048,"XER ABI");
_Static_assert(offsetof(ppu_context,cia)==1064,"CIA ABI");
_Static_assert(sizeof(ppu_context)==1104,"context sizeof");
extern int ppu_f_00010000(ppu_context*);
extern int ppu_f_00010024(ppu_context*);
extern int ppu_f_00010100(ppu_context*);
#define CHECK(x) do {if(!(x)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(void){
  CHECK(ar_bridge_init(256*1024)==AR_OK);
  CHECK(ar_register(0x10000,ppu_f_00010000)==AR_OK);
  CHECK(ar_register(0x10024,ppu_f_00010024)==AR_OK);
  CHECK(ar_register(0x10100,ppu_f_00010100)==AR_OK);
  CHECK(ar_registered_count()==3);
  CHECK(ar_register(0x10024,ppu_f_00010024)==AR_DUPLICATE);
  ppu_context c={0};c.lr=0x1234;
  CHECK(ar_run(&c,0x10000,10)==AR_OK);
  CHECK(c.gpr[3]==14&&c.lr==0x1234&&c.cia==0x1234);
  CHECK(ar_last_error()==0);
  ar_write32(0x200,0x12345678);
  CHECK(ar_read8(0x200)==0x12&&ar_read16(0x200)==0x1234);
  CHECK(ar_read32(0x200)==0x12345678);
  ar_write64(0x208,0x0102030405060708ULL);
  CHECK(ar_read8(0x209)==0x02&&ar_read64(0x208)==0x0102030405060708ULL);
  CHECK(ar_run(&c,0x10100,10)==AR_UNRESOLVED);
  CHECK(ar_last_unresolved()==0x10200);
  CHECK(ar_run(&c,0x10000,1)==AR_BUDGET);
  ar_write64(0x40000,99);
  CHECK(ar_last_error()==AR_MEM_FAULT);
  ar_bridge_shutdown();CHECK(ar_bridge_init(8192)==AR_OK);
  CHECK(ar_registered_count()==0);
  CHECK(ar_run(&c,0x10000,1)==AR_UNRESOLVED);
  ar_bridge_shutdown();
  puts("PASS: canonical PPU state, nested dispatch, TOC/LR, guest BE memory, missing entry, budget, OOB");
  return 0;
}
