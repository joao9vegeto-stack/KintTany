/* Synthetic guest registers/memory. No actual PS3 file calls are invented. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m759_register_owner(const uint8_t*,size_t);
extern int ar_m759_native_002c1378(ppu_context*);
static const uint32_t original[42] = {UINT32_C(0x60000000),
 UINT32_C(0x3c800084),
 UINT32_C(0x607e0000),
 UINT32_C(0x3ca00002),
 UINT32_C(0x30de0020),
 UINT32_C(0x60a5d1e4),
 UINT32_C(0x8064b0a8),
 UINT32_C(0x3b200000),
 UINT32_C(0x80630008),
 UINT32_C(0x907e1c4c),
 UINT32_C(0x8064b0a8),
 UINT32_C(0x63840000),
 UINT32_C(0x80e3000c),
 UINT32_C(0x81030004),
 UINT32_C(0x7ce700d0),
 UINT32_C(0x78c30020),
 UINT32_C(0x90be0000),
 UINT32_C(0x7cc83810),
 UINT32_C(0x933e001c),
 UINT32_C(0x38a0001f),
 UINT32_C(0x30c60200),
 UINT32_C(0x90de1c50),
 UINT32_C(0x4826a471),
 UINT32_C(0x60000000),
 UINT32_C(0x3c600085),
 UINT32_C(0x9b3e003f),
 UINT32_C(0x7c9fd014),
 UINT32_C(0x5766053e),
 UINT32_C(0x3084fffc),
 UINT32_C(0x2c060000),
 UINT32_C(0x80a3ae5c),
 UINT32_C(0x90be000c),
 UINT32_C(0x93c3ae5c),
 UINT32_C(0x93fe0010),
 UINT32_C(0x909e0018),
 UINT32_C(0x93fe0014),
 UINT32_C(0x93fe0004),
 UINT32_C(0x93fe0008),
 UINT32_C(0x83bdb0ac),
 UINT32_C(0x90de1c44),
 UINT32_C(0x7fbdf810),
 UINT32_C(0x41820088)};
static uint32_t guest[42] = {UINT32_C(0x60000000),
 UINT32_C(0x3c800084),
 UINT32_C(0x607e0000),
 UINT32_C(0x3ca00002),
 UINT32_C(0x30de0020),
 UINT32_C(0x60a5d1e4),
 UINT32_C(0x8064b0a8),
 UINT32_C(0x3b200000),
 UINT32_C(0x80630008),
 UINT32_C(0x907e1c4c),
 UINT32_C(0x8064b0a8),
 UINT32_C(0x63840000),
 UINT32_C(0x80e3000c),
 UINT32_C(0x81030004),
 UINT32_C(0x7ce700d0),
 UINT32_C(0x78c30020),
 UINT32_C(0x90be0000),
 UINT32_C(0x7cc83810),
 UINT32_C(0x933e001c),
 UINT32_C(0x38a0001f),
 UINT32_C(0x30c60200),
 UINT32_C(0x90de1c50),
 UINT32_C(0x4826a471),
 UINT32_C(0x60000000),
 UINT32_C(0x3c600085),
 UINT32_C(0x9b3e003f),
 UINT32_C(0x7c9fd014),
 UINT32_C(0x5766053e),
 UINT32_C(0x3084fffc),
 UINT32_C(0x2c060000),
 UINT32_C(0x80a3ae5c),
 UINT32_C(0x90be000c),
 UINT32_C(0x93c3ae5c),
 UINT32_C(0x93fe0010),
 UINT32_C(0x909e0018),
 UINT32_C(0x93fe0014),
 UINT32_C(0x93fe0004),
 UINT32_C(0x93fe0008),
 UINT32_C(0x83bdb0ac),
 UINT32_C(0x90de1c44),
 UINT32_C(0x7fbdf810),
 UINT32_C(0x41820088)};
static ar_ppu_fn installed;
static uint32_t call_count;
static uint64_t call_target;
static uint32_t mem_writes;
int ar_m712_exec_window(const uint8_t*elf,size_t sz,uint32_t pc,uint32_t o[6]){
 if(!elf||sz<64u||pc<0x002c1378u||pc>=0x002c1420u||
    ((pc-0x002c1378u)&3u))return AR_BAD_ARGS;
 memset(o,0,sizeof(uint32_t)*6u);
 const unsigned start=(pc-0x002c1378u)/4u;
 const unsigned n=start+4u>42u?42u-start:4u;
 for(unsigned k=0;k<n;k++)o[k]=original[start+k];
 o[4]=n;o[5]=5;return AR_OK;
}
uint32_t ar_read32(uint64_t pc){
 if(pc>=0x002c1378u&&pc<0x002c1420u&&!((pc-0x002c1378u)&3u))
   return guest[(pc-0x002c1378u)/4u];
 return 0u;
}
void ar_write32(uint64_t addr,uint32_t x){(void)addr;(void)x;mem_writes++;}
void ar_write8(uint64_t addr,uint8_t x){(void)addr;(void)x;mem_writes++;}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 if(pc!=0x002c1378u||installed)return AR_DUPLICATE;
 installed=fn;return AR_OK;
}
int ar_guest_call(ppu_context*c,uint64_t pc){
 if(!c||pc!=UINT64_C(0x0052b840)||c->lr!=0x002c13d4ULL)return -99;
 call_count++;call_target=pc;c->gpr[3]=0;
 return AR_OK;
}
static int scenario(uint64_t r27,uint32_t target){
 ppu_context c={0};
 c.gpr[27]=r27;c.gpr[28]=0x2000;c.gpr[30]=0x3000;
 c.gpr[31]=0x4000;c.gpr[3]=1;c.gpr[6]=0x5000;c.gpr[5]=0x1234;
 c.ctr=0x55;call_count=0;mem_writes=0;
 const int ret=installed(&c);
 if(ret!=AR_TAIL||c.cia!=target||c.lr!=0x002c13d4u||
    c.ctr!=0x55||call_count!=1||call_target!=0x0052b840u||
    mem_writes<5u)return 1;
 return 0;
}
int main(void){
 uint8_t fake_elf[64]={0};
 guest[5]^=1u;
 if(ar_m759_register_owner(fake_elf,sizeof(fake_elf))==AR_OK||installed)return 1;
 guest[5]^=1u;
 if(ar_m759_register_owner(fake_elf,sizeof(fake_elf))!=AR_OK||!installed)return 2;
 if(scenario(0u,0x002c14a4u))return 3; /* taken cr0.EQ */
 if(scenario(1u,0x002c1420u))return 4; /* not taken */
 puts("M7.59: authenticated 42 PPC guest words, native BL call target and both conditional BC successors, zero interpretation PASS");
 return 0;
}
