/* Authentic one-word frontier AOT, synthetic 128-bit PPC guest vectors. */
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m752_native_003b0608(ppu_context*);
extern int ar_m752_register_vsldoi(const uint8_t*,size_t);
static uint32_t elf_word=0x105ff82c,vm_word=0x105ff82c;
static ar_ppu_fn installed;
int ar_m712_exec_window(const uint8_t*elf,size_t len,uint32_t pc,uint32_t words[6]){
 if(!elf||len<64||pc!=0x003b0608u)return AR_BAD_ARGS;
 memset(words,0,6*sizeof(*words));words[0]=elf_word;words[4]=1;words[5]=1;
 return AR_OK;
}
uint32_t ar_read32(uint64_t pc){return pc==0x003b0608u?vm_word:0u;}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 if(pc!=0x003b0608u||installed)return AR_DUPLICATE;
 installed=fn;return AR_OK;
}
static int equals(ppu_context *c,unsigned r,const uint8_t *bytes){
 for(unsigned i=0;i<16u;i++)if(ar_vmx_byte(c,r,i)!=bytes[i])return 0;
 return 1;
}
int main(void){
 uint8_t owner[64]={0};
 if(ar_m752_register_vsldoi(NULL,64)!=AR_BAD_ARGS)return 1;
 vm_word^=1u;
 if(ar_m752_register_vsldoi(owner,64)!=AR_BAD_ARGS||installed)return 2;
 vm_word^=1u;elf_word^=1u;
 if(ar_m752_register_vsldoi(owner,64)!=AR_BAD_ARGS||installed)return 3;
 elf_word^=1u;
 if(ar_m752_register_vsldoi(owner,64)!=AR_OK||!installed)return 4;
 ppu_context c={0};c.lr=0xabcdu;c.ctr=9;c.gpr[3]=0x55u;
 uint8_t a[16],b[16],out[16];
 for(unsigned i=0;i<16u;i++){
  a[i]=(uint8_t)i;b[i]=(uint8_t)(0xa0u+i);
  ar_vmx_setbyte(&c,31u,i,a[i]);
  ar_vmx_setbyte(&c,30u,i,b[i]);
 }
 /* Original owner has shift=0, vd=2; must be exact VR31 copy. */
 if(installed(&c)!=AR_TAIL||c.cia!=0x003b060cu||
    c.lr!=0xabcdu||c.ctr!=9||c.gpr[3]!=0x55u||!equals(&c,2u,a))
  return 5;
 /* General VMX generic helper exercises nonzero shift, alias and bounds. */
 if(ar_vmx_vsldoi(&c,30u,31u,30u,7u)!=AR_OK)return 6;
 for(unsigned i=0;i<16u;i++)out[i]=(i+7u<16u)?a[i+7u]:b[i+7u-16u];
 if(!equals(&c,30u,out))return 7;
 if(ar_vmx_vsldoi(&c,31u,31u,30u,16u)!=AR_PPC_UNSUPPORTED)
  return 8;
 puts("M7.52 owner VSLDOI: original opcode authenticated; 128-bit bytes, offset, alias, no fake guest sys_fs PASS");
 return 0;
}
