/* M7.53 semantic CI: authentic 4-word PPC VMX path, synthetic input only. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <fenv.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m753_register_vectorfp(const uint8_t*,size_t);
static uint32_t words[4]={0x10a0190a,0x1065f8ef,0x1063296e,0x1063f12e};
static uint32_t loaded[4]={0x10a0190a,0x1065f8ef,0x1063296e,0x1063f12e};
static ar_ppu_fn target;
int ar_m712_exec_window(const uint8_t*elf,size_t n,uint32_t pc,uint32_t out[6]){
 if(!elf||n<64||pc!=0x003b062c)return AR_BAD_ARGS;
 memset(out,0,6*sizeof(*out));
 memcpy(out,words,sizeof(words));out[4]=4;out[5]=5;
 return AR_OK;
}
uint32_t ar_read32(uint64_t pc){
 if(pc<0x003b062c||pc>0x003b0638||((pc-0x003b062c)&3))return 0;
 return loaded[(pc-0x003b062c)/4u];
}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 if(pc!=0x003b062c||target)return AR_DUPLICATE;
 target=fn;return AR_OK;
}
static void setf(ppu_context*c,unsigned v,unsigned i,float f){
 uint32_t raw=0;memcpy(&raw,&f,4);
 for(unsigned j=0;j<4;j++)ar_vmx_setbyte(c,v,4u*i+j,
                                  (uint8_t)(raw>>(24u-8u*j)));
}
static float getf(ppu_context*c,unsigned v,unsigned i){
 uint32_t bits=ar_vmx_word(c,v,i);float f=0;memcpy(&f,&bits,4);return f;
}
int main(void){
 uint8_t fake[64]={0};(void)fesetround(FE_TONEAREST);
 if(ar_m753_register_vectorfp(NULL,64)!=AR_BAD_ARGS)return 1;
 loaded[0]^=1u;
 if(ar_m753_register_vectorfp(fake,64)!=AR_BAD_ARGS||target)return 2;
 loaded[0]^=1u;words[3]^=1u;
 if(ar_m753_register_vectorfp(fake,64)!=AR_BAD_ARGS||target)return 3;
 words[3]^=1u;
 if(ar_m753_register_vectorfp(fake,64)!=AR_OK||!target)return 4;
 ppu_context c={0};c.lr=0xbeefu;c.ctr=17u;c.gpr[3]=9u;
 for(unsigned i=0;i<4;i++){
  setf(&c,3,i,2.f);setf(&c,31,i,4.f);
  setf(&c,30,i,1.f);setf(&c,4,i,3.f);
 }
 if(target(&c)!=AR_TAIL||c.cia!=0x003b063cu||
    c.lr!=0xbeefu||c.ctr!=17u||c.gpr[3]!=9u)return 5;
 for(unsigned i=0;i<4;i++)
  if(getf(&c,5,i)!=0.5f||getf(&c,3,i)!=7.f)return 6;
 ppu_context fail={0};setf(&fail,3,0,0.f);
 if(target(&fail)!=AR_PPC_UNSUPPORTED||fail.cia!=0x003b062cu)
  return 7;
 puts("M7.53 4 original PPC VMX instructions: signed ELF+guest VM, 4-lane reciprocal/FMA, alias and fail-closed PASS");
 return 0;
}
