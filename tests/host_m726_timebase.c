/* M7.26 genuine LV2 syscall 147 and PPC64 divdu ABI synthetic tests.
 * No commercial ELF, game instructions, secrets or PRX supplied.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_lv2_bootstrap.h"
static void be16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void be32(uint8_t*p,uint32_t x){
 p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);
 p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;
}
static void be64(uint8_t*p,uint64_t x){be32(p,(uint32_t)(x>>32));be32(p+4,(uint32_t)x);}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
 be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t *ph=elf+64;be32(ph,1);be32(ph+4,5);
 be64(ph+8,0x200);be64(ph+16,0x1000);
 be64(ph+32,0x100);be64(ph+40,0x100);
 be32(elf+0x200,UINT32_C(0x39600093)); /* li r11,147 */
 be32(elf+0x204,UINT32_C(0x44000002)); /* sc */
 be32(elf+0x208,UINT32_C(0x4e800020)); /* blr */
 if(ar_bridge_init(0x3000)!=AR_OK)return 1;
 if(ar_vm_load(0x1000,elf+0x200,0x100)!=AR_OK)return 2;
 if(ar_ppc_fallback_attach(elf,sizeof(elf),32,ar_ppc_fallback_step)!=AR_OK)return 3;
 ar_lv2_bootstrap_reset();
 ppu_context cpu={0};cpu.lr=0x1100u;cpu.gpr[2]=0xdeadbeefu;
 if(ar_lv2_timebase_frequency(NULL)!=AR_BAD_ARGS ||
    ar_lv2_timebase_queries()!=0)return 4;
 if(ar_bind_syscall(147,ar_lv2_timebase_frequency)!=AR_OK)return 5;
 if(ar_run(&cpu,0x1000,32)!=AR_OK ||
    cpu.gpr[3]!=UINT64_C(79800000)||
    cpu.gpr[2]!=0xdeadbeefu||
    ar_lv2_timebase_queries()!=1u)return 6;
 ar_aot_trace t={0};ar_trace_snapshot(&t);
 if(t.lv2_calls!=1u || t.lv2_last_number!=147u ||
    t.lv2_last_pc!=0x1004u||t.lv2_missing_number!=0u||
    t.lv2_missing_pc!=0u||t.fallback_steps!=3u ||
    t.aot_dispatches!=0u)return 7;
 /* Next syscall remains unknown and must record true number and PC. */
 be32(elf+0x200,UINT32_C(0x39600094)); /* li r11,148 */
 if(ar_vm_load(0x1000,elf+0x200,4)!=AR_OK)return 8;
 memset(&cpu,0,sizeof(cpu));cpu.lr=0x1100u;
 if(ar_run(&cpu,0x1000,32)!=AR_MISSING_LV2||
    ar_last_missing_syscall()!=148u)return 9;
 ar_trace_snapshot(&t);
 if(t.lv2_calls!=1u||t.lv2_last_number!=148u||
    t.lv2_missing_number!=148u||t.lv2_last_pc!=0x1004u||
    t.lv2_missing_pc!=0x1004u)return 10;
 /* Invalid sc encoding cannot silently turn into a syscall. */
 be32(elf+0x204,UINT32_C(0x44000000));
 if(ar_vm_load(0x1004,elf+0x204,4)!=AR_OK)return 11;
 memset(&cpu,0,sizeof(cpu));cpu.lr=0x1100u;
 if(ar_run(&cpu,0x1000,32)!=AR_PPC_UNSUPPORTED)return 12;
 ar_trace_snapshot(&t);
 if(t.lv2_calls!=0u||t.fallback_unsupported_pc!=0x1004u ||
    t.fallback_unsupported_word!=UINT32_C(0x44000000))return 13;
 /* A direct step after an expected fault must start in a reset VM:
  * ar_last_error stays sticky until ar_run/init, by design. */
 ar_bridge_shutdown();
 if(ar_bridge_init(0x3000)!=AR_OK)return 18;
 /* Full-width unsigned DIVDU for synthetic PPC64 RS/RA/RB. */
 be32(elf+0x200,UINT32_C(0x7c641b92)); /* divdu r3,r4,r3 */
 if(ar_vm_load(0x1000,elf+0x200,4)!=AR_OK)return 14;
 memset(&cpu,0,sizeof(cpu));
 cpu.gpr[3]=2u;cpu.gpr[4]=UINT64_C(0x8000000000000000);
 uint32_t observed=0u;
 if(ar_ppc_fallback_step(&cpu,elf,sizeof(elf),0x1000,&observed)!=AR_TAIL||
    cpu.gpr[3]!=UINT64_C(0x4000000000000000))return 15;
 cpu.gpr[3]=0u;cpu.gpr[4]=42u;
 if(ar_ppc_fallback_step(&cpu,elf,sizeof(elf),0x1000,&observed)!=AR_PPC_UNSUPPORTED ||
    cpu.gpr[4]!=42u)return 16;
 ar_lv2_bootstrap_reset();
 if(ar_lv2_timebase_queries()!=0u)return 17;
 ar_bridge_shutdown();
 puts("M7.26 PS3 LV2 147 timebase, DIVDU64, missing syscall PC, fail-closed PASS");
 return 0;
}
