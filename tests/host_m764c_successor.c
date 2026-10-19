/* Real original GOWA ELF 0x005392A4: native C CFG, compare + stores + BO/BI.
   Tests both conditional successors, with no PPC fallback/interpreter. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m764c_native_005392a4(ppu_context*);
static uint64_t stack[64];
static unsigned writes;
static int fault;
int ar_last_error(void){return fault;}
void ar_write64(uint64_t ea,uint64_t val){
 if(ea<UINT64_C(0x1000)||ea>=UINT64_C(0x1200)||(ea&7u)){fault=AR_MEM_FAULT;return;}
 stack[(ea-UINT64_C(0x1000))/8u]=val;writes++;
}
static int test(uint64_t input, uint64_t dest){
 ppu_context c;memset(&c,0,sizeof(c));memset(stack,0,sizeof(stack));
 writes=0;fault=0;c.gpr[1]=UINT64_C(0x1100);c.gpr[3]=input;
 c.gpr[4]=UINT64_C(0xffff);c.gpr[29]=UINT64_C(0x1234);
 c.lr=UINT64_C(0x11224455);
 int rc=ar_m764c_native_005392a4(&c);
 if(rc!=AR_TAIL||c.cia!=dest||c.gpr[1]!=UINT64_C(0x1070)||
    c.gpr[0]!=UINT64_C(0xffff)||c.gpr[9]!=UINT64_C(0xffff)||
    c.lr!=UINT64_C(0x11224455)||writes!=3u) return 1;
 return 0;
}
int main(void){
 if(test(1u,UINT64_C(0x00539308))||test(2u,UINT64_C(0x005392D0))){
  fputs("M7.64.1 native successor FAIL\n",stderr);return 1;
 }
 puts("M7.64.1 real 0x005392A4: native STDU/STD, CR7/CR1, LR, both BC edges PASS");
 return 0;
}
