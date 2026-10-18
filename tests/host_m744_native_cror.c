/* M7.44: host-native test of actual owner PPC CROR + conditional
 * branch, with registration provenance and fail-closed byte checks.
 * Synthetic test fixture: never opens proprietary ELF/game files.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m744_native_003f2860(ppu_context*);
extern int ar_m744_register_owner(const uint8_t*,size_t);
static uint32_t owner[2]={UINT32_C(0x4c402b82),UINT32_C(0x41820008)};
static uint32_t guest[2]={UINT32_C(0x4c402b82),UINT32_C(0x41820008)};
static ar_ppu_fn registered;
static unsigned registration_count;
int ar_m712_exec_window(const uint8_t*elf,size_t size,uint32_t pc,uint32_t out[6]){
 if(!elf||size<64u||pc!=UINT32_C(0x003f2860)||!out)return AR_BAD_ARGS;
 memset(out,0,sizeof(uint32_t)*6u);
 out[0]=owner[0];out[1]=owner[1];out[4]=2;out[5]=1;
 return AR_OK;
}
uint32_t ar_read32(uint64_t address){
 if(address==UINT64_C(0x003f2860))return guest[0];
 if(address==UINT64_C(0x003f2864))return guest[1];
 return 0u;
}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t address,ar_ppu_fn fn){
 if(address!=UINT32_C(0x003f2860)||fn!=ar_m744_native_003f2860)
   return AR_BAD_ARGS;
 registered=fn;registration_count++;
 return AR_OK;
}
int main(void){
 uint8_t fake_elf[64]={0};
 if(ar_m744_register_owner(NULL,64u)!=AR_BAD_ARGS ||
    ar_m744_register_owner(fake_elf,8u)!=AR_BAD_ARGS)return 1;
 owner[0]^=1u;
 if(ar_m744_register_owner(fake_elf,sizeof(fake_elf))!=AR_BAD_ARGS)return 2;
 owner[0]^=1u;guest[1]^=4u;
 if(ar_m744_register_owner(fake_elf,sizeof(fake_elf))!=AR_BAD_ARGS)return 3;
 guest[1]^=4u;
 if(ar_m744_register_owner(fake_elf,sizeof(fake_elf))!=AR_OK ||
    registration_count!=1u||!registered)return 4;
 if(registered(NULL)!=AR_BAD_ARGS)return 5;
 for(unsigned src0=0;src0<2u;src0++)for(unsigned src5=0;src5<2u;src5++)
 for(unsigned old_dest=0;old_dest<2u;old_dest++){
   ppu_context c={0};
   for(unsigned i=0;i<32u;i++)c.gpr[i]=UINT64_C(0x1234567800000000)+i;
   c.cr=(UINT32_C(0x12345678)&~(UINT32_C(1)<<31u)
         &~(UINT32_C(1)<<26u)&~(UINT32_C(1)<<29u))
         |(src0<<31u)|(src5<<26u)|(old_dest<<29u);
   c.xer=UINT32_C(0xa0000000);
   c.lr=UINT64_C(0x1234567887654321);
   c.ctr=UINT64_C(0x0badc0ffee001122);
   c.cia=UINT64_C(0x003f2860);
   ppu_context before=c;
   const uint32_t cond=src0|src5;
   if(registered(&c)!=AR_TAIL)return 6;
   if(c.cr!=((before.cr&~(UINT32_C(1)<<29u))|(cond<<29u))||
      c.cia!=(cond?UINT64_C(0x003f286c):UINT64_C(0x003f2868)))
     return 7;
   before.cr=c.cr;before.cia=c.cia;
   if(memcmp(&c,&before,sizeof(c))!=0)return 8;
 }
 puts("M7.44 owner PPC CROR+BC native C AOT: 8 CR source/destination vectors, VM/ELF mismatch blocked, LR/CTR/XER/GPR unchanged PASS");
 return 0;
}
