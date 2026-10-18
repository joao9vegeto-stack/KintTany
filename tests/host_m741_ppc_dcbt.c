/* M7.41 PowerPC64 DCBT/DCBTST architectural semantics, using synthetic
 * BE ELF executable instructions. Cache hints do not modify architectural
 * state and may be ignored as hints; UNKNOWN opcodes remain rejected.
 * This is fallback interpreter evidence, NEVER counted as native AOT.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_ppc_fallback_step(ppu_context*,const uint8_t*,size_t,
                                uint32_t,uint32_t*);
static void w16(uint8_t*p,uint16_t v){p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v;}
static void w32(uint8_t*p,uint32_t v){
 p[0]=(uint8_t)(v>>24);p[1]=(uint8_t)(v>>16);
 p[2]=(uint8_t)(v>>8);p[3]=(uint8_t)v;
}
static void w64(uint8_t*p,uint64_t v){w32(p,(uint32_t)(v>>32));w32(p+4,(uint32_t)v);}
int main(void){
 /* three actual (observed M7.40) DCBT words, one DCBTST variant,
  * followed by unsupported reserved Rc=1. */
 const uint32_t code[]={
   UINT32_C(0x7c00222c), UINT32_C(0x7c06222c),
   UINT32_C(0x7c00022c), UINT32_C(0x7c0021ec),
   UINT32_C(0x7c00222d)
 };
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 w16(elf+16,2);w16(elf+18,21);w32(elf+20,1);
 w64(elf+32,64);w16(elf+54,56);w16(elf+56,1);
 uint8_t *ph=elf+64;
 w32(ph,1);w32(ph+4,5);w64(ph+8,0x200);w64(ph+16,0x1000);
 w64(ph+32,sizeof(code));w64(ph+40,sizeof(code));
 for(size_t i=0;i<sizeof(code)/sizeof(code[0]);i++)
   w32(elf+0x200+i*4,code[i]);
 if(ar_bridge_init(0x10000u)!=AR_OK)return 1;
 if(ar_vm_load(0x1000,elf+0x200,sizeof(code))!=AR_OK)return 2;
 ppu_context c={0};for(unsigned i=0;i<32;i++)c.gpr[i]=UINT64_C(0xABCDE0000)+i;
 c.gpr[4]=UINT64_C(0x0000000000fffffc);
 c.gpr[6]=UINT64_C(0x0000000100000000);
 c.xer=UINT32_C(0x87654321);c.cr=UINT32_C(0xfdb97531);
 c.lr=UINT64_C(0x123456789abcdef0);
 c.ctr=UINT64_C(0x876543210fedcba9);
 c.cia=0x1000;
 ppu_context initial=c;
 for(size_t i=0;i<4;i++){
   const uint32_t pc=0x1000u+(uint32_t)(i*4u);
   uint32_t decoded=0u;
   if(ar_ppc_fallback_step(&c,elf,sizeof(elf),pc,&decoded)!=AR_TAIL
      ||decoded!=code[i]||c.cia!=pc+4u||
      memcmp(c.gpr,initial.gpr,sizeof(c.gpr))!=0||
      c.xer!=initial.xer||c.cr!=initial.cr||
      c.lr!=initial.lr||c.ctr!=initial.ctr)return (int)(10+i);
 }
 /* Reject invalid Rc bit with unchanged PC and no guest effects. */
 uint32_t decoded=0;
 if(ar_ppc_fallback_step(&c,elf,sizeof(elf),0x1010u,&decoded)!=AR_PPC_UNSUPPORTED
    ||decoded!=code[4]||c.cia!=0x1010u)return 20;
 if(memcmp(c.gpr,initial.gpr,sizeof(c.gpr))!=0 ||
    c.xer!=initial.xer||c.cr!=initial.cr)return 21;
 ar_bridge_shutdown();
 puts("M7.41 PPC DCBT/DCBTST cache-hint semantics: 4 synthetic original-pattern opcodes, 0 GPR/CR/XER/memory mutations, Rc invalid rejected PASS");
 return 0;
}
