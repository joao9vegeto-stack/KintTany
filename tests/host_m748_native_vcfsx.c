/* M7.48 synthetic guest VM verifies genuine 31 PPC vector startup AOT. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m748_native_003ddf20(ppu_context*);
extern int ar_m748_native_003ddf54(ppu_context*);
extern int ar_m748_register_owner(const uint8_t*,size_t);
static uint32_t owner[31]={
UINT32_C(0x3c60003e),UINT32_C(0x3c80009c),UINT32_C(0x3863ded0),UINT32_C(0x38a078b0),UINT32_C(0x38c00010),UINT32_C(0x3d00009d),UINT32_C(0x38e00020),UINT32_C(0x7c4018ce),UINT32_C(0x7c4521ce),UINT32_C(0x39200030),UINT32_C(0x7c4618ce),UINT32_C(0x388080d0),UINT32_C(0x3ca0009d),UINT32_C(0x1040134a),UINT32_C(0x38c080e0),UINT32_C(0x3d40009d),UINT32_C(0x396080f0),UINT32_C(0x39800040),UINT32_C(0x7c4441ce),UINT32_C(0x7c4718ce),UINT32_C(0x1040134a),UINT32_C(0x3c80009d),UINT32_C(0x38e08100),UINT32_C(0x7c4629ce),UINT32_C(0x7c4918ce),UINT32_C(0x1040134a),UINT32_C(0x7c4b51ce),UINT32_C(0x7c4c18ce),UINT32_C(0x1040134a),UINT32_C(0x7c4721ce),UINT32_C(0x4e800020)
};
static uint32_t vmwords[31];
static uint8_t guest[0xA00000u];
static int fault,registrations;
static ar_ppu_fn functions[2];
int ar_m712_exec_window(const uint8_t*e,size_t len,uint32_t pc,uint32_t w[6]){
 if(!e||len<64u||pc<0x003ddf20u||pc>0x003ddf98u||((pc-0x003ddf20u)&3u))
   return AR_BAD_ARGS;
 memset(w,0,sizeof(uint32_t)*6u);
 const unsigned from=(pc-0x003ddf20u)/4u;
 const unsigned n=31u-from<4u?31u-from:4u;
 for(unsigned i=0;i<n;i++)w[i]=owner[from+i];
 w[4]=n;w[5]=1u;return AR_OK;
}
uint32_t ar_read32(uint64_t pc){
 if(pc>=0x003ddf20u&&pc<=0x003ddf98u&&!(pc&3u))
    return vmwords[(pc-0x003ddf20u)/4u];
 return 0u;
}
int ar_last_error(void){return fault;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 static const uint32_t addr[]={0x003ddf20u,0x003ddf54u};
 if(registrations>=2||pc!=addr[registrations])return AR_DUPLICATE;
 functions[registrations++]=fn;return AR_OK;
}
int ar_vm_load(uint64_t addr,const void*data,size_t n){
 if(addr>sizeof(guest)||n>sizeof(guest)-addr){fault=AR_MEM_FAULT;return AR_MEM_FAULT;}
 memcpy(guest+(size_t)addr,data,n);return AR_OK;
}
int ar_vm_read_bytes(uint64_t addr,void*dst,size_t n){
 if(addr>sizeof(guest)||n>sizeof(guest)-addr){fault=AR_MEM_FAULT;return AR_MEM_FAULT;}
 memcpy(dst,guest+(size_t)addr,n);return AR_OK;
}
static void words_at(unsigned addr,const uint32_t v[4]){
 for(unsigned k=0;k<4;k++)
  for(unsigned j=0;j<4;j++)
   guest[addr+k*4+j]=(uint8_t)(v[k]>>(24u-j*8u));
}
static uint32_t be32(unsigned addr){
 return ((uint32_t)guest[addr]<<24)|((uint32_t)guest[addr+1]<<16)|
        ((uint32_t)guest[addr+2]<<8)|guest[addr+3];
}
int main(void){
 uint8_t fake[64]={0};
 memcpy(vmwords,owner,sizeof(owner));
 if(ar_m748_register_owner(NULL,64)!=AR_BAD_ARGS)return 1;
 owner[13]^=1u;
 if(ar_m748_register_owner(fake,64)!=AR_BAD_ARGS||registrations)return 2;
 owner[13]^=1u;
 vmwords[29]^=1u;
 if(ar_m748_register_owner(fake,64)!=AR_BAD_ARGS||registrations)return 3;
 vmwords[29]^=1u;
 if(ar_m748_register_owner(fake,64)!=AR_OK||registrations!=2)return 4;
 const uint32_t input[4]={0u,0xffffffffu,0x01000001u,0x80000000u};
 words_at(0x003dded0u,input);
 words_at(0x003ddee0u,input);
 words_at(0x003ddef0u,input);
 words_at(0x003ddf00u,input);
 words_at(0x003ddf10u,input);
 ppu_context c={0};
 c.lr=UINT64_C(0x00555554);
 if(functions[0](&c)!=AR_TAIL||c.cia!=0x00555554u)return 5;
 if(c.gpr[3]!=0x003dded0u||c.gpr[4]!=0x009d0000u)return 6;
 /* Conversion 0, -1, 16777217 tie-to-even, INT32_MIN */
 const uint32_t expected[4]={0x00000000u,0xbf800000u,
                              0x4b800000u,0xcf000000u};
 for(unsigned i=0;i<4u;i++){
   if(be32(0x009c80f0u+i*4)!=expected[i] ||
      be32(0x009c8100u+i*4)!=expected[i])return 7;
 }
 if(be32(0x009c78b0u)!=input[0]||be32(0x009c78b0u+8)!=input[2])return 8;
 if(c.ctr || c.xer || c.fpscr || c.cr)return 9;
 ppu_context suffix={0};
 suffix.lr=0x00300110u;suffix.gpr[3]=0x003dded0u;
 suffix.gpr[4]=(uint64_t)(int64_t)(int16_t)0x80d0u;
 suffix.gpr[5]=0x009d0000u;suffix.gpr[7]=32u;
 suffix.gpr[8]=0x009d0000u;suffix.gpr[9]=48u;
 for(unsigned i=0;i<4u;i++)for(unsigned j=0;j<4u;j++)
   ar_vmx_setbyte(&suffix,2,i*4+j,(uint8_t)(input[i]>>(24u-8u*j)));
 if(functions[1](&suffix)!=AR_TAIL||suffix.cia!=0x00300110u)return 10;
 if(be32(0x009c8100u+8)!=expected[2])return 11;
 ppu_context bad={0};
 bad.gpr[3]=sizeof(guest);bad.lr=0x300110u;
 if(functions[1](&bad)!=AR_MEM_FAULT)return 12;
 if(ar_vmx_vcfsx_lane(16777217,0)!=0x4b800000u ||
    ar_vmx_vcfsx_lane(1,1)!=0x3f000000u ||
    ar_vmx_vcfsx_lane(-2147483647-1,0)!=0xcf000000u)return 13;
 puts("M7.48 native 31-PPC VCFSX: ELF/VM owner authenticated, two real native entrypoints; IEEE RN ties-even, alias-safe VMX, guest stores, errors PASS");
 return 0;
}
