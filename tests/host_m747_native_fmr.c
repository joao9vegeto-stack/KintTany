/* M7.47 FMR owner AOT isolated tests over synthetic ELF/guest VM. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include "ppu_bridge.h"
extern int ar_m747_native_003eef0c(ppu_context*);
extern int ar_m747_native_003eef20(ppu_context*);
extern int ar_m747_register_owner(const uint8_t*,size_t);
static const uint32_t orig[]={
 0xfc20f890u,0xfc40f890u,0xfc60f890u,0x4bff6b3du,
 0x60000000u,0x3c60009du,0x3c800068u,0xfc20f890u,0x38a00000u,
 0xfc40f890u,0x39000000u,0xfc60f890u,0x3063b228u,
 0x3084fa6cu,0x4bff6b11u
};
static uint32_t elfwords[15],vmwords[15];
static int registered,calls,call_fail;
static ar_ppu_fn fn[2];
int ar_m712_exec_window(const uint8_t*e,size_t len,uint32_t pc,uint32_t out[6]){
 if(!e||len<64u||!out||pc<0x003eef0cu||pc>0x003eef44u||((pc-0x003eef0cu)&3u))
  return AR_BAD_ARGS;
 const size_t ix=(pc-0x003eef0cu)/4u;
 const unsigned n=(unsigned)(15u-ix<4u?15u-ix:4u);
 memset(out,0,sizeof(uint32_t)*6u);
 for(unsigned i=0;i<n;i++)out[i]=elfwords[ix+i];
 out[4]=n;out[5]=5u;return AR_OK;
}
uint32_t ar_read32(uint64_t pc){
 if(pc<0x003eef0cu||pc>0x003eef40u||((pc-0x003eef0cu)&3u))return 0;
 return vmwords[(pc-0x003eef0cu)/4u];
}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn f){
 static const uint32_t addr[]={0x003eef0cu,0x003eef20u};
 if(registered>=2||pc!=addr[registered])return AR_DUPLICATE;
 fn[registered++]=f;return AR_OK;
}
int ar_guest_call(ppu_context *c,uint64_t target){
 if(!c||target!=0x003e5a54u)return AR_BAD_ARGS;
 calls++;return call_fail?AR_PPC_UNSUPPORTED:AR_OK;
}
static uint64_t readbits(const double*p){uint64_t v;memcpy(&v,p,8);return v;}
static void putbits(double*p,uint64_t v){memcpy(p,&v,8);}
int main(void){
 uint8_t fake[64]={0};memcpy(elfwords,orig,sizeof(orig));memcpy(vmwords,orig,sizeof(orig));
 if(ar_m747_register_owner(NULL,64)!=AR_BAD_ARGS)return 1;
 elfwords[4]^=1u;
 if(ar_m747_register_owner(fake,64)!=AR_BAD_ARGS||registered)return 2;
 elfwords[4]^=1u;vmwords[14]^=1u;
 if(ar_m747_register_owner(fake,64)!=AR_BAD_ARGS||registered)return 3;
 vmwords[13]^=1u;
 if(ar_m747_register_owner(fake,64)!=AR_OK||registered!=2)return 4;
 static const uint64_t bits[]={0x7ff800000000cafeULL,0x8000000000000000ULL,
                                  0x7ff0000000000000ULL,0x3ff0000000000000ULL};
 for(unsigned j=0;j<4;j++){
  ppu_context c={0};
  putbits(&c.fpr[31],bits[j]);c.cr=0x12345678u;c.fpscr=0x98765432u;
  c.xer=0x84321765u;c.ctr=0x12345678u;c.gpr[3]=0x123u;c.lr=0x911u;
  if(fn[0](&c)!=AR_TAIL||calls!=(int)j+1||
     c.cia!=0x003eef1cu||c.lr!=0x003eef1cu)return 5;
  for(unsigned k=1;k<=3;k++)if(readbits(&c.fpr[k])!=bits[j])return 6;
  if(c.cr!=0x12345678u||c.fpscr!=0x98765432u||
     c.xer!=0x84321765u||c.ctr!=0x12345678u||c.gpr[3]!=0x123u)return 7;
 }
 ppu_context c={0};putbits(&c.fpr[31],bits[0]);c.xer=0;
 if(fn[1](&c)!=AR_TAIL||c.cia!=0x003eef48u||c.lr!=0x003eef48u||
    c.gpr[3]!=0x009cb228u||c.gpr[4]!=0x0067fa6cu||
    c.gpr[5]!=0||c.gpr[8]!=0||
    !(c.xer&0x20000000u))return 8;
 for(unsigned k=1;k<=3;k++)if(readbits(&c.fpr[k])!=bits[0])return 9;
 call_fail=1;
 if(fn[0](&c)!=AR_PPC_UNSUPPORTED)return 10;
 puts("M7.47 native FMR owner: 4+10 verified real PPC words, FPR bit-copy incl NaN payload, negative zero, Inf; GPR/CR/FPSCR preserved, guest-call errors and ELF/VM mismatch guarded PASS");
 return 0;
}
