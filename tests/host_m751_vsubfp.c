/* M7.51 real-owner vsubfp AOT gated by exact original opcode,
 * with synthetic VR inputs (never game content). */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <fenv.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m751_register_vsubfp(const uint8_t*,size_t);
extern int ar_m751_native_003b0604(ppu_context*);
static uint32_t original=0x1062184a,loaded=0x1062184a;
static ar_ppu_fn installed;
int ar_m712_exec_window(const uint8_t*d,size_t len,uint32_t pc,uint32_t w[6]){
 if(!d||len<64||pc!=0x003b0604)return AR_BAD_ARGS;
 memset(w,0,6*sizeof(*w));w[0]=original;w[4]=1;w[5]=1;
 return AR_OK;
}
uint32_t ar_read32(uint64_t at){return at==0x003b0604?loaded:0u;}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 if(pc!=0x003b0604||installed)return AR_DUPLICATE;
 installed=fn;return AR_OK;
}
static void vecf(ppu_context *c,unsigned vr,unsigned i,float f){
 uint32_t word=0;memcpy(&word,&f,4);
 for(unsigned j=0;j<4;j++)ar_vmx_setbyte(c,vr,i*4+j,
                                         (uint8_t)(word>>(24-8*j)));
}
static float getf(ppu_context *c,unsigned vr,unsigned i){
 uint32_t w=ar_vmx_word(c,vr,i);float f;memcpy(&f,&w,4);return f;
}
int main(void){
 uint8_t fake[64]={0};fesetround(FE_TONEAREST);
 loaded^=1u;
 if(ar_m751_register_vsubfp(fake,64)!=AR_BAD_ARGS||installed)return 1;
 loaded^=1u;
 if(ar_m751_register_vsubfp(fake,64)!=AR_OK||!installed)return 2;
 ppu_context c={0};c.lr=0xdead; c.gpr[3]=0xbeef;
 for(unsigned i=0;i<4u;i++){
   vecf(&c,2u,i,(float)(8+i));
   vecf(&c,3u,i,(float)(1+i));
 }
 if(installed(&c)!=AR_TAIL||c.cia!=0x003b0608||
    c.lr!=0xdead||c.gpr[3]!=0xbeef)return 3;
 for(unsigned i=0;i<4u;i++)if(getf(&c,3u,i)!=7.0f)return 4;
 c.cia=0;vecf(&c,2u,0,__builtin_inff());
 if(installed(&c)!=AR_PPC_UNSUPPORTED||c.cia!=0x003b0604)return 5;
 puts("M7.51 real 0x003B0604 vsubfp signed AOT: 4 lanes, alias, unsupported exceptional states PASS");
 return 0;
}
