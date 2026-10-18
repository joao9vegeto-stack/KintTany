/* M7.50 synthetic CPU+VM asserts actual 24-owner-PPC AOT semantics.
 * No GOWA.ELF or commercial PSARC is linked into test artifacts. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <fenv.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m750_native_003b1d78(ppu_context*);
extern int ar_m750_native_003b1dc4(ppu_context*);
extern int ar_m750_register_owner(const uint8_t*,size_t);
static const uint32_t auth[]={
 0xec21f828u,0xd03f0490u,0x7d2549ceu,0x7d0649ceu,
 0x7d4749ceu,0x7d6049ceu,0x7d8551ceu,0x7da651ceu,
 0x7c0751ceu,0x7c2051ceu,0x7c4521ceu,0x7c6621ceu,
 0x7ca721ceu,0x7c8021ceu,0x93df0484u,0x911f04a0u,
 0x939f0488u,0x999f04a4u,0x93df0504u,0x308304b4u,
 0x30630004u,0x78840020u,0x93c40000u,0x4200fff0u};
static uint32_t exe[24],memcode[24];
static unsigned registered;
static ar_ppu_fn functions[2];
static uint8_t guest[0x800000u];
static int fault;
int ar_m712_exec_window(const uint8_t*elf,size_t len,uint32_t pc,uint32_t out[6]){
 if(!elf||len<64u||pc<0x003b1d78u||pc>0x003b1dd4u||
    ((pc-0x003b1d78u)&3u))return AR_BAD_ARGS;
 const unsigned i=(pc-0x003b1d78u)/4u;
 const unsigned n=(24u-i<4u)?24u-i:4u;
 memset(out,0,6*sizeof(uint32_t));
 for(unsigned j=0;j<n;j++)out[j]=exe[i+j];
 out[4]=n;out[5]=1u;return AR_OK;
}
uint32_t ar_read32(uint64_t ea){
 if(ea>=0x003b1d78u&&ea<=0x003b1dd4u&&!(ea&3u))
    return memcode[(ea-0x003b1d78u)/4u];
 if(ea>=sizeof(guest)-3u){fault=AR_MEM_FAULT;return 0u;}
 return ((uint32_t)guest[ea]<<24)|((uint32_t)guest[ea+1u]<<16)|
        ((uint32_t)guest[ea+2u]<<8)|guest[ea+3u];
}
void ar_write32(uint64_t ea,uint32_t w){
 if(ea>sizeof(guest)-4u){fault=AR_MEM_FAULT;return;}
 for(unsigned j=0;j<4u;j++)guest[ea+j]=(uint8_t)(w>>(24u-8u*j));
}
void ar_write8(uint64_t ea,uint8_t w){
 if(ea>=sizeof(guest)){fault=AR_MEM_FAULT;return;}
 guest[ea]=w;
}
int ar_vm_load(uint64_t ea,const void *data,size_t n){
 if(ea>sizeof(guest)||n>sizeof(guest)-ea){fault=AR_MEM_FAULT;return AR_MEM_FAULT;}
 memcpy(guest+ea,data,n);return AR_OK;
}
int ar_vm_read_bytes(uint64_t ea,void *out,size_t n){
 if(ea>sizeof(guest)||n>sizeof(guest)-ea){fault=AR_MEM_FAULT;return AR_MEM_FAULT;}
 memcpy(out,guest+ea,n);return AR_OK;
}
int ar_last_error(void){int v=fault;fault=0;return v;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 const uint32_t target[]={0x003b1d78u,0x003b1dc4u};
 if(registered>=2u||pc!=target[registered])return AR_DUPLICATE;
 functions[registered++]=fn;return AR_OK;
}
int main(void){
 uint8_t elf[64]={0};
 memcpy(exe,auth,sizeof(auth));memcpy(memcode,auth,sizeof(auth));
 if(ar_m750_register_owner(NULL,64)!=AR_BAD_ARGS)return 1;
 exe[0]^=1u;
 if(ar_m750_register_owner(elf,64)!=AR_BAD_ARGS||registered)return 2;
 exe[0]^=1u;
 memcode[23]^=1u;
 if(ar_m750_register_owner(elf,64)!=AR_BAD_ARGS||registered)return 3;
 memcode[23]^=1u;
 if(ar_m750_register_owner(elf,64)!=AR_OK||registered!=2u)return 4;
 ppu_context c={0};
 fesetround(FE_TONEAREST);
 c.fpr[1]=4.0;c.fpr[31]=1.0;c.gpr[31]=0x500000u;
 c.gpr[30]=0xaabbccdd;c.gpr[28]=0xbabe;c.gpr[8]=0x41u;
 c.gpr[12]=0x12u;c.gpr[5]=0x100u;c.gpr[6]=0x200u;
 c.gpr[7]=0x300u;c.gpr[9]=0x2000u;c.gpr[10]=0x3000u;
 c.gpr[4]=0x4000u;c.gpr[3]=0x1000u;c.ctr=3;c.lr=0x550010u;
 for(unsigned v=0;v<14;v++)
  for(unsigned i=0;i<16;i++)
    ar_vmx_setbyte(&c,v,i,(uint8_t)(v*17u+i));
 if(functions[0](&c)!=AR_TAIL||c.cia!=0x003b1dc4u||
    c.fpr[1]!=3.0||c.ctr!=3||c.lr!=0x550010u)return 5;
 if(ar_read32(0x500000u+1168u)!=0x40400000u ||
    ar_read32(0x500000u+1156u)!=0xaabbccddu ||
    ar_read32(0x500000u+1184u)!=0x41u ||
    guest[0x500000u+1188u]!=0x12u)return 6;
 for(unsigned i=0;i<16u;i++)
   if(guest[0x2100u+i]!=(uint8_t)(9u*17u+i))return 7;
 if(functions[1](&c)!=AR_TAIL||c.cia!=0x003b1dd8u||
    c.ctr!=0u||c.gpr[3]!=0x100cu||
    ar_read32(0x14b4u)!=0xaabbccddu||
    ar_read32(0x14b8u)!=0xaabbccddu||
    ar_read32(0x14bcu)!=0xaabbccddu||
    c.lr!=0x550010u)return 8;
 ppu_context bad={0};bad.gpr[31]=UINT64_C(0xffffffffffffff00);
 bad.fpr[1]=2.;bad.fpr[31]=1.;
 if(functions[0](&bad)!=AR_MEM_FAULT)return 9;
 printf("M7.50 original 24-PPC AOT: authenticated ELF/VM + native fsubs/stfs/12STVX/CTR-bdnz, BE real memory, no fake cellFs PASS\n");
 return 0;
}
