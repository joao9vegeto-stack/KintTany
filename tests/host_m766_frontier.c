/* Strict M7.66 PPC64 original ELF front, native C host semantics.
   Host guest memory is synthetic; on-device execution is not inferred. */
#include "ppu_bridge.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_m766_native_005394e8(ppu_context*);
extern int ar_m766_native_00669a84(ppu_context*);
extern int ar_m766_native_00669aac(ppu_context*);
extern int ar_m766_native_0053950c(ppu_context*);
extern int ar_m766_native_00522938(ppu_context*);
#define REQUIRE(cond,why) do{if(!(cond)){fputs("M7.66 FAIL: " why "\n",stderr);return __LINE__;}}while(0)
int main(void){
 ppu_context c;memset(&c,0,sizeof(c));
 REQUIRE(ar_bridge_init(11042816u)==AR_OK,"guest RAM init");
 const uint64_t oldsp=UINT64_C(0xa87c20);
 const uint64_t toc=UINT64_C(0x83f2b0);
 ar_write32(UINT64_C(0x839b14),UINT32_C(0xa389c8));
 ar_write32(UINT64_C(0x839b10),UINT32_C(0xa38888));
 ar_write32(UINT64_C(0x828298),UINT32_C(0x900000));
 ar_write32(UINT64_C(0x900000),UINT32_C(0x53950c));
 ar_write32(UINT64_C(0x900004),UINT32_C(0x83f2b0));
 REQUIRE(ar_last_error()==AR_OK,"guest memory initialization");
 c.gpr[1]=oldsp;c.gpr[2]=toc;c.gpr[3]=UINT64_C(0xa38a3c);
 c.lr=UINT64_C(0x539608);c.ctr=UINT64_C(0x1234);c.cr=UINT32_C(0x22000042);
 REQUIRE(ar_m766_native_005394e8(&c)==AR_TAIL,"boot block tail");
 REQUIRE(c.cia==UINT64_C(0x669a84),"real direct BL target");
 REQUIRE(c.lr==UINT64_C(0x53950c),"BL link register");
 REQUIRE(c.gpr[1]==oldsp-112,"guest STDU update r1");
 REQUIRE(c.gpr[9]==UINT64_C(0xa389c8),"lwz TOC guest big endian");
 REQUIRE(c.gpr[3]==UINT64_C(0xa38a20),"addi r3, r9, +88");
 REQUIRE(c.gpr[4]==UINT64_C(0xa38888),"second lwz TOC");
 REQUIRE(ar_read32(UINT64_C(0xa38a38))==2u,"stw zero/dword sign and BE");
 REQUIRE(ar_read64(oldsp+16)==UINT64_C(0x539608),"saved LR stack BE");
 REQUIRE(ar_m766_native_00669a84(&c)==AR_TAIL,"real thunk bctrl");
 REQUIRE(c.ctr==UINT64_C(0x53950c) && c.cia==UINT64_C(0x53950c),"computed CTR target from guest descriptor");
 REQUIRE(c.lr==UINT64_C(0x669aac),"bctrl link register");
 REQUIRE(c.gpr[2]==toc,"guest descriptor TOC");
 REQUIRE(ar_m766_native_00669aac(&c)==AR_TAIL,"real thunk epilogue");
 REQUIRE(c.lr==UINT64_C(0x53950c)&&c.cia==c.lr,"restored LR/BLR");
 REQUIRE(c.gpr[2]==toc,"restored TOC");
 uint32_t keep=c.cr & ~UINT32_C(0xF);
 c.gpr[3]=5;
 REQUIRE(ar_m766_native_0053950c(&c)==AR_TAIL,"return conditional native");
 REQUIRE(c.cia==UINT64_C(0x539528),"BO6 branch on CR7 EQ false");
 REQUIRE((c.cr&UINT32_C(0xF))==4u,"CR7 GT field correct");
 REQUIRE((c.cr&~UINT32_C(0xF))==keep,"other CR fields preserved");
 c.gpr[3]=0;
 REQUIRE(ar_m766_native_0053950c(&c)==AR_TAIL,"return conditional false");
 REQUIRE(c.cia==UINT64_C(0x539518),"BO6 not taken with CR7 EQ");
 c.gpr[3]=(uint64_t)(int64_t)-5;c.gpr[2]=toc;c.xer=0;
 ar_write32(toc-23308,0x11223344u);
 REQUIRE(ar_m766_native_00522938(&c)==AR_TAIL,"SRAWI direct block");
 REQUIRE(c.gpr[30]==UINT64_C(0xffffffffffffffff),"SRAWI signed shift");
 REQUIRE((c.xer&UINT32_C(0x20000000))!=0,"XER carry bit after negative shifted-out PPC word");
 REQUIRE(ar_last_error()==AR_OK,"no fake guest memory faults");
 ar_bridge_shutdown();
 puts("M7.66 GOWA native 0x005394E8: BE guest LWZ/STW/STDU, real indirect BCTRL/LR/TOC/CTR, BO6 CR7, SRAWI XER PASS");
 return 0;
}
