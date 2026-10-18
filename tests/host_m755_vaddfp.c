#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <fenv.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
static void setf(ppu_context*c,unsigned r,unsigned i,float f){
 uint32_t w=0;memcpy(&w,&f,4u);
 for(unsigned k=0;k<4u;k++)
   ar_vmx_setbyte(c,r,4u*i+k,(uint8_t)(w>>(24u-8u*k)));
}
static float getf(ppu_context*c,unsigned r,unsigned i){
 uint32_t bits=ar_vmx_word(c,r,i);float v;memcpy(&v,&bits,4u);return v;
}
int main(void){
 ppu_context c={0};
 if(fesetround(FE_TONEAREST))return 1;
 for(unsigned i=0;i<4u;i++){
   setf(&c,8u,i,1.0f+(float)i);
   setf(&c,7u,i,2.0f);
 }
 if(ar_vmx_vaddfp(&c,8u,8u,7u)!=AR_OK)return 2;
 for(unsigned i=0;i<4u;i++)
   if(getf(&c,8u,i)!=(float)i+3.0f)return 3;
 setf(&c,7u,0u,__builtin_inff());
 if(ar_vmx_vaddfp(&c,8u,8u,7u)!=AR_PPC_UNSUPPORTED)return 4;
 puts("M7.55 VMX VADDFP finite arithmetic, register alias and fail-closed special values PASS");
 return 0;
}
