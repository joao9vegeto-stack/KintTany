/* Synthetic, host-native owner block test: no proprietary file needed. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m745_native_0052ba70(ppu_context*);
extern int ar_m745_register_owner(const uint8_t*,size_t);
static uint32_t words[6]={0x7d290430u,0x2f870000u,0x7d694878u,
0x39430004u,0x91230000u,0x419e0030u};
static uint32_t vm[6]={0x7d290430u,0x2f870000u,0x7d694878u,
0x39430004u,0x91230000u,0x419e0030u};
static ar_ppu_fn fn;static int err,store_count,reg_count;
static uint64_t store_addr;static uint32_t stored;
int ar_m712_exec_window(const uint8_t*e,size_t len,uint32_t pc,uint32_t out[6]){
 if(!e||len<64||!out||(pc!=0x0052ba70u&&pc!=0x0052ba80u))return AR_BAD_ARGS;
 memset(out,0,6*sizeof(uint32_t));
 const unsigned from=(pc-0x0052ba70u)/4u,n=from?2u:4u;
 for(unsigned i=0;i<n;i++)out[i]=words[from+i];
 out[4]=n;out[5]=1;return AR_OK;
}
uint32_t ar_read32(uint64_t addr){
 if(addr<0x0052ba70u||addr>0x0052ba84u||((addr-0x0052ba70u)&3u))return 0;
 return vm[(addr-0x0052ba70u)/4u];
}
void ar_write32(uint64_t addr,uint32_t val){store_addr=addr;stored=val;store_count++;}
int ar_last_error(void){return err?AR_MEM_FAULT:AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn ptr){
 if(pc!=0x0052ba70u||ptr!=ar_m745_native_0052ba70)return AR_BAD_ARGS;
 fn=ptr;reg_count++;return AR_OK;
}
int main(void){
 uint8_t fake[64]={0};
 if(ar_m745_register_owner(NULL,64)!=AR_BAD_ARGS||
    ar_m745_register_owner(fake,8)!=AR_BAD_ARGS)return 1;
 words[0]^=1;
 if(ar_m745_register_owner(fake,64)!=AR_BAD_ARGS)return 2;
 words[0]^=1;vm[5]^=1;
 if(ar_m745_register_owner(fake,64)!=AR_BAD_ARGS)return 3;
 vm[5]^=1;
 if(ar_m745_register_owner(fake,64)!=AR_OK||!fn||reg_count!=1)return 4;
 if(fn(NULL)!=AR_BAD_ARGS)return 5;
 const unsigned shifts[]={0,1,7,31,32,33,63,64};
 for(unsigned j=0;j<8;j++)
 for(int cmp=-1;cmp<=1;cmp++)
 for(unsigned so=0;so<2;so++){
   ppu_context c={0};
   for(unsigned k=0;k<32;k++)c.gpr[k]=0x1234000000000000ULL+k;
   c.gpr[0]=shifts[j];c.gpr[3]=0x1000u;
   c.gpr[7]=cmp<0?UINT64_MAX:cmp>0?1u:0u;
   c.gpr[9]=0xdeadbeeffedcba98ULL;
   c.gpr[11]=0xf000f000caca0000ULL;
   c.cr=0x12345678u;c.xer=0x20000000u|(so?0x80000000u:0u);
   c.lr=0x1122334455667788ULL;c.ctr=0x123456789abcdef0ULL;
   const uint64_t lr=c.lr,ctr=c.ctr;const uint32_t xer=c.xer;
   const unsigned sh=shifts[j]&63u;
   const uint64_t srw=sh>=32u?0u:(uint64_t)(0xfedcba98u>>sh);
   const uint64_t result=c.gpr[11]&~srw;
   const uint32_t low=(cmp<0?8u:cmp>0?4u:2u)|so;
   const int oldstores=store_count;
   if(fn(&c)!=AR_TAIL||store_count!=oldstores+1)return 6;
   if(c.gpr[9]!=result||c.gpr[10]!=0x1004u||
      c.cr!=((0x12345678u&~15u)|low)||
      c.cia!=(cmp==0?0x0052bab4u:0x0052ba88u)||
      c.lr!=lr||c.ctr!=ctr||c.xer!=xer||
      store_addr!=0x1000u||stored!=(uint32_t)result)return 7;
 }
 ppu_context faulty={0};faulty.gpr[3]=0x1000;err=1;
 if(fn(&faulty)!=AR_MEM_FAULT)return 8;
 puts("M7.45 native PPC SRW/CMPDI/ANDC/ADDI/STW/BC: 48 vectors; ELF/VM mismatch and write errors blocked PASS");
 return 0;
}
