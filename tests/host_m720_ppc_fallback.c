/* M7.20 synthetic PPC64 BE code and real native-dispatch + fallback tests.
 * The test never uses the commercial ELF, owner's secret or game data.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
static void be16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void be32(uint8_t*p,uint32_t x){p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;}
static void be64(uint8_t*p,uint64_t x){be32(p,(uint32_t)(x>>32));be32(p+4,(uint32_t)x);}
static int fake_aot(ppu_context*c){
 c->gpr[9]=12u;c->gpr[7]=4u;c->cia=0x1004;return AR_TAIL;
}
static int fake_not_equal(ppu_context*c){
 c->gpr[9]=13u;c->gpr[7]=4u;c->cia=0x1004;return AR_TAIL;
}
static int fake_div_zero(ppu_context*c){
 c->gpr[9]=12u;c->gpr[7]=0u;c->cia=0x1004;return AR_TAIL;
}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
 be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t*ph=elf+64;be32(ph,1);be32(ph+4,5);
 be64(ph+8,0x200);be64(ph+16,0x1000);be64(ph+32,0x100);be64(ph+40,0x100);
 const uint32_t words[]={
  UINT32_C(0x60000000), /* AOT intercept at 0x1000 */
  UINT32_C(0x30c90004), /* addic r6,r9,4 */
  UINT32_C(0x7cc63b96), /* divwu r6,r6,r7 */
  UINT32_C(0x7cc639d6), /* mullw r6,r6,r7 */
  UINT32_C(0x7cc64810), /* subfc r6,r6,r9 */
  UINT32_C(0x30c60004), /* addic r6,r6,4 */
  UINT32_C(0x2c060000), /* cmpwi cr0,r6,0 */
  UINT32_C(0x41820008), /* beq 0x1024 */
  UINT32_C(0xffffffff), /* unsupported on fallthrough */
  UINT32_C(0x4e800020)  /* blr */
 };
 for(unsigned i=0;i<sizeof(words)/sizeof(words[0]);i++)
    be32(elf+0x200+4u*i,words[i]);
 if(ar_bridge_init(0x3000)!=AR_OK)return 1;
 if(ar_vm_load(0x1000,elf+0x200,0x100)!=AR_OK)return 2;
 if(ar_register(0x1000,fake_aot)!=AR_OK)return 3;
 ppu_context c={0};c.lr=0x1000;
 if(ar_run(&c,0x1000,64)!=AR_UNRESOLVED ||
    ar_last_unresolved()!=0x1004)return 4; /* default OFF */
 ar_aot_trace tr={0};ar_trace_snapshot(&tr);
 if(tr.aot_dispatches!=1||tr.fallback_steps!=0||tr.unique_aot!=1)return 5;
 if(ar_ppc_fallback_attach(elf,sizeof(elf),16,ar_ppc_fallback_step)!=AR_OK)return 6;
 memset(&c,0,sizeof(c));c.lr=0x1000;
 if(ar_run(&c,0x1000,64)!=AR_OK)return 7;
 ar_trace_snapshot(&tr);
 if(tr.aot_dispatches!=1||tr.unique_aot!=1||
    tr.fallback_steps!=8||tr.fallback_unsupported_pc||
    tr.fallback_last_pc!=0x1024u||c.gpr[6]!=0u||
    !(c.cr&UINT32_C(0x20000000)))return 8;
 if(ar_run(&c,0x1000,1)!=AR_BUDGET)return 9;
 ar_trace_snapshot(&tr);
 if(tr.aot_dispatches!=1||tr.fallback_steps!=0)return 10;
 ar_bridge_shutdown();
 if(ar_bridge_init(0x3000)!=AR_OK)return 11;
 if(ar_vm_load(0x1000,elf+0x200,0x100)!=AR_OK ||
    ar_register(0x1000,fake_not_equal)!=AR_OK)return 12;
 if(ar_ppc_fallback_attach(elf,sizeof(elf),16,ar_ppc_fallback_step)!=AR_OK)return 13;
 memset(&c,0,sizeof(c));c.lr=0x1000;
 if(ar_run(&c,0x1000,64)!=AR_PPC_UNSUPPORTED ||
    ar_last_unresolved()!=0x1020u)return 14;
 ar_trace_snapshot(&tr);
 if(tr.aot_dispatches!=1||tr.fallback_steps!=7u||
    tr.fallback_unsupported_pc!=0x1020u||
    tr.fallback_unsupported_word!=UINT32_C(0xffffffff))return 15;
 ar_bridge_shutdown();
 if(ar_bridge_init(0x3000)!=AR_OK)return 16;
 if(ar_vm_load(0x1000,elf+0x200,0x100)!=AR_OK ||
    ar_register(0x1000,fake_div_zero)!=AR_OK)return 17;
 if(ar_ppc_fallback_attach(elf,sizeof(elf),16,ar_ppc_fallback_step)!=AR_OK)return 18;
 memset(&c,0,sizeof(c));
 if(ar_run(&c,0x1000,64)!=AR_PPC_UNSUPPORTED ||
    ar_last_unresolved()!=0x1008)return 19;
 ar_trace_snapshot(&tr);
 if(tr.fallback_steps!=1u||tr.fallback_unsupported_word!=UINT32_C(0x7cc63b96))return 20;
 ar_bridge_shutdown();
 if(ar_bridge_init(0x3000)!=AR_OK)return 21;
 if(ar_vm_load(0x1000,elf+0x200,0x100)!=AR_OK ||
    ar_register(0x1000,fake_aot)!=AR_OK ||
    ar_ppc_fallback_attach(elf,sizeof(elf),2,ar_ppc_fallback_step)!=AR_OK)return 22;
 memset(&c,0,sizeof(c));
 if(ar_run(&c,0x1000,64)!=AR_PPC_LIMIT ||
    ar_last_unresolved()!=0x100cu)return 23;
 ar_trace_snapshot(&tr);
 if(tr.fallback_steps!=2u||tr.fallback_step_limit!=2u)return 24;
 ar_bridge_shutdown();
 puts("M7.20 signed hybrid AOT priority, PPC divwu/mullw/subfc, fail-closed and budget PASS");
 return 0;
}
