#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "ppu_bridge.h"
#include "ppu_fp_scalar.h"
extern int ar_m754_register_fcmp_branch(const uint8_t*,size_t);
static const uint32_t expected[2]={0xfc01f800,0x41810018};
static uint32_t vm[2]={0xfc01f800,0x41810018};
static ar_ppu_fn registered;
int ar_m712_exec_window(const uint8_t*data,size_t n,uint32_t pc,uint32_t out[6]){
 if(!data||n<64||pc!=0x003b064c)return AR_BAD_ARGS;
 memset(out,0,6*sizeof(*out));
 out[0]=expected[0];out[1]=expected[1];out[4]=4;out[5]=5;return AR_OK;
}
uint32_t ar_read32(uint64_t pc){
 if(pc==0x003b064c)return vm[0];
 if(pc==0x003b0650)return vm[1];
 return 0;
}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 if(pc!=0x003b064c||registered)return AR_DUPLICATE;
 registered=fn;return AR_OK;
}
static int branch(double a,double b,uint32_t cc,uint64_t pc){
 ppu_context c={0};
 c.fpr[1]=a;c.fpr[31]=b;c.cr=0x00ffffff;
 c.lr=0xbeef;c.ctr=17;c.fpscr=0x80000000;
 if(registered(&c)!=AR_TAIL||c.cia!=pc||
    ((c.cr>>28)&15)!=cc||((c.fpscr>>12)&15)!=cc||
    c.lr!=0xbeef||c.ctr!=17||c.fpr[1]!=a||c.fpr[31]!=b)return -1;
 return 0;
}
int main(void){
 uint8_t fake[64]={0};
 if(ar_m754_register_fcmp_branch(NULL,64)!=AR_BAD_ARGS)return 1;
 vm[0]^=1;
 if(ar_m754_register_fcmp_branch(fake,64)!=AR_BAD_ARGS||registered)return 2;
 vm[0]^=1;
 if(ar_m754_register_fcmp_branch(fake,64)!=AR_OK||!registered)return 3;
 if(branch(3,2,4,0x003b0668)||branch(2,3,8,0x003b0654)||
    branch(2,2,2,0x003b0654))return 4;
 ppu_context c={0};c.cr=0xaabbccdd;c.fpscr=0x88001234;
 ar_fp_setraw(&c,1,UINT64_C(0x7ff8000000000001));
 c.fpr[31]=5.0;
 if(ar_fp_compare(&c,4,1,31,0)!=AR_OK||
    ((c.cr>>12)&15)!=1||((c.fpscr>>12)&15)!=1)return 5;
 c.cr=0xaabbccdd;c.fpscr=0x88001234;
 if(ar_fp_compare(&c,4,1,31,1)!=AR_PPC_UNSUPPORTED||
    c.cr!=0xaabbccdd||c.fpscr!=0x88001234)return 6;
 ar_fp_setraw(&c,1,UINT64_C(0x7ff0000000000001));
 if(ar_fp_compare(&c,4,1,31,0)!=AR_PPC_UNSUPPORTED)return 7;
 c.fpr[1]=3;c.fpr[31]=4;
 if(ar_fp_compare(&c,7,1,31,1)!=AR_OK||((c.cr>>0)&15)!=8)
  return 8;
 puts("M7.54 owner FCMPU/BC and generic FCMPU/FCMPO: LT/GT/EQ/UN, CR/FPSCR, both real successors, fail-closed PASS");
 return 0;
}
