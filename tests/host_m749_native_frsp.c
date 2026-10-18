/* M7.49 native FRSP owner authenticity and FPR/FPSCR tests. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <fenv.h>
#include "ppu_bridge.h"
extern int ar_m749_register_frsp(const uint8_t*,size_t);
extern int ar_m749_native_003b1d5c(ppu_context*);
static uint32_t elfword=0xfc200818u,vmword=0xfc200818u;
static int registered;
int ar_m712_exec_window(const uint8_t*e,size_t len,uint32_t pc,uint32_t w[6]){
 if(!e||len<64||pc!=0x003b1d5cu)return AR_BAD_ARGS;
 memset(w,0,6*sizeof(uint32_t));w[0]=elfword;w[4]=1;w[5]=1;return AR_OK;
}
uint32_t ar_read32(uint64_t addr){
 return addr==0x003b1d5cu?vmword:0u;
}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 if(pc!=0x003b1d5cu||fn!=ar_m749_native_003b1d5c||registered)
    return AR_DUPLICATE;
 registered=1;return AR_OK;
}
static uint64_t raw(ppu_context*c,unsigned reg){
 uint64_t bits;memcpy(&bits,&c->fpr[reg],8);return bits;
}
int main(void){
 uint8_t fake[64]={0};fesetround(FE_TONEAREST);
 if(ar_m749_register_frsp(NULL,64)!=AR_BAD_ARGS)return 1;
 elfword^=1u;
 if(ar_m749_register_frsp(fake,64)!=AR_BAD_ARGS||registered)return 2;
 elfword^=1u;vmword^=1u;
 if(ar_m749_register_frsp(fake,64)!=AR_BAD_ARGS||registered)return 3;
 vmword^=1u;
 if(ar_m749_register_frsp(fake,64)!=AR_OK||registered!=1)return 4;
 const double values[]={0.0,-0.0,1.0,-4.5,16777217.0,-16777217.0};
 for(unsigned i=0;i<sizeof(values)/sizeof(values[0]);i++){
  ppu_context c={0};c.fpr[1]=values[i];c.gpr[3]=42;c.lr=0x451234;c.cr=0x22222222;
  if(ar_m749_native_003b1d5c(&c)!=AR_TAIL)return 5;
  if(c.cia!=0x003b1d60u || c.lr!=0x451234 ||
     c.gpr[3]!=42 || c.cr!=0x22222222)return 6;
  double expected=(double)(float)values[i];
  uint64_t bits;memcpy(&bits,&expected,8);
  if(raw(&c,1)!=bits)return 7;
  if(i>=4 && !(c.fpscr&0x82020000u))return 8;
 }
 ppu_context reject={0};reject.fpr[1]=1.0;reject.fpscr=1u;
 if(ar_m749_native_003b1d5c(&reject)!=AR_PPC_UNSUPPORTED)return 9;
 puts("M7.49 FRSP owner AOT: 1 original PPC instruction, native bit-accurate FPSCR-default rounding, signed zero, tie-to-even, ELF/VM tamper blocked PASS");
 return 0;
}
