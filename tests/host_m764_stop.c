#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m764_native_00539378(ppu_context*);
int main(void){
 ppu_context c;memset(&c,0,sizeof(c));c.gpr[4]=UINT64_C(0xDEADBEEF);
 if(ar_m764_native_00539378(&c)!=AR_TAIL||c.cia!=UINT64_C(0x005392A4)||
    c.gpr[3]!=1u||c.gpr[4]!=UINT64_C(0xFFFF)||c.lr!=0u){
  fputs("M7.64 native GOWA guest block semantic FAILURE\n",stderr);return 1;
 }
 puts("M7.64 original GOWA 0x00539378 native ALU, clrldi and B tail PASS");
 return 0;
}
