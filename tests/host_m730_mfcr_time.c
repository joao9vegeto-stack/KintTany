/* M7.30 synthetic PowerPC MFCR + LV2 #145 (wall-clock),
 * no commercial ELF, no firmware, no game asset.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_lv2_bootstrap.h"
static void b16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void b32(uint8_t*p,uint32_t x){p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;}
static void b64(uint8_t*p,uint64_t x){b32(p,(uint32_t)(x>>32));b32(p+4,(uint32_t)x);}
static void put(uint8_t*elf,uint32_t n,unsigned slot){b32(elf+0x200+slot*4u,n);}
static int upload(uint8_t*elf,size_t bytes){return ar_vm_load(0x1000,elf+0x200,bytes);}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 b16(elf+16,2);b16(elf+18,21);b32(elf+20,1);
 b64(elf+32,64);b16(elf+54,56);b16(elf+56,1);
 uint8_t*ph=elf+64;b32(ph,1);b32(ph+4,5);
 b64(ph+8,0x200);b64(ph+16,0x1000);
 b64(ph+32,0x100);b64(ph+40,0x100);
 if(ar_bridge_init(0x4000)!=AR_OK)return 1;
 ar_lv2_bootstrap_reset();
 /* Exactly the MFCR from the physical report, plus synthetic #145. */
 put(elf,UINT32_C(0x7d800026),0);
 put(elf,UINT32_C(0x39600091),1);
 put(elf,UINT32_C(0x44000002),2);
 put(elf,UINT32_C(0x4e800020),3);
 if(upload(elf,16)!=AR_OK)return 2;
 if(ar_ppc_fallback_attach(elf,sizeof(elf),64,ar_ppc_fallback_step)!=AR_OK)return 3;
 if(ar_bind_syscall(145u,ar_lv2_current_time)!=AR_OK)return 4;
 ppu_context cpu={0};
 cpu.lr=0x1100;cpu.gpr[3]=0x1800;cpu.gpr[4]=0x1810;
 cpu.gpr[12]=UINT64_MAX;cpu.cr=UINT32_C(0xa5e8f03d);
 cpu.xer=UINT32_C(0xe0000000);cpu.gpr[2]=UINT64_C(0x12345678);
 if(ar_run(&cpu,0x1000,64)!=AR_OK)return 5;
 const uint64_t sec=ar_read64(0x1800),nsec=ar_read64(0x1810);
 if(sec<UINT64_C(1500000000)||nsec>=UINT64_C(1000000000)||
    cpu.gpr[3]!=0||cpu.gpr[4]!=0x1810u||
    cpu.gpr[12]!=UINT32_C(0xa5e8f03d)||
    cpu.cr!=UINT32_C(0xa5e8f03d)||cpu.xer!=UINT32_C(0xe0000000)||
    cpu.gpr[2]!=UINT64_C(0x12345678)||
    ar_lv2_current_time_queries()!=1u)return 6;
 ar_aot_trace tr={0};ar_trace_snapshot(&tr);
 if(tr.lv2_calls!=1||tr.lv2_last_number!=145||
    tr.lv2_last_pc!=0x1008u||tr.lv2_missing_number||
    tr.fallback_steps!=4||tr.aot_dispatches!=0||
    tr.fallback_trace_count!=4||tr.fallback_trace_pcs[0]!=0x1000||
    tr.fallback_trace_words[0]!=UINT32_C(0x7d800026)||
    tr.fallback_trace_pcs[2]!=0x1008u||
    tr.fallback_trace_pcs[3]!=0x100cu)return 7;
 /* Both arguments must validate BEFORE any buffer is modified. */
 cpu.gpr[3]=0x1900;cpu.gpr[4]=0xfffffff0u;
 if(ar_lv2_current_time_values(&cpu,12345,987654321)!=AR_MEM_FAULT ||
    ar_read64(0x1900)!=0)return 8;
 cpu.gpr[3]=0x1900;cpu.gpr[4]=0x1910;
 if(ar_lv2_current_time_values(&cpu,UINT64_C(0x1122334455667788),
                                UINT64_C(0x000000003ade68b1))!=AR_OK||
    cpu.gpr[3]!=0||ar_read64(0x1900)!=UINT64_C(0x1122334455667788)||
    ar_read64(0x1910)!=UINT64_C(0x000000003ade68b1))return 9;
 cpu.gpr[3]=0x1900;cpu.gpr[4]=0x1900;
 if(ar_lv2_current_time_values(&cpu,1,2)!=AR_BAD_ARGS)return 10;
 if(ar_lv2_current_time_queries()!=2)return 11;
 /* An invalid partial-MFOCRF must fail closed rather than read CR. */
 put(elf,UINT32_C(0x7d900026),0);
 if(upload(elf,4)!=AR_OK)return 12;
 memset(&cpu,0,sizeof(cpu));cpu.lr=0x1100;cpu.gpr[12]=77;
 if(ar_run(&cpu,0x1000,64)!=AR_PPC_UNSUPPORTED)return 13;
 ar_trace_snapshot(&tr);
 if(tr.fallback_unsupported_pc!=0x1000||
    tr.fallback_unsupported_word!=UINT32_C(0x7d900026)||
    cpu.gpr[12]!=77||tr.fallback_trace_count!=0)return 14;
 /* Ring stores the last 32 *executed* instructions in arrival order. */
 for(unsigned i=0;i<40;i++)put(elf,UINT32_C(0x60000000),i);
 put(elf,UINT32_C(0x4e800020),40);
 if(upload(elf,41u*4u)!=AR_OK)return 15;
 memset(&cpu,0,sizeof(cpu));cpu.lr=0x1100;
 if(ar_run(&cpu,0x1000,64)!=AR_OK)return 16;
 ar_trace_snapshot(&tr);
 if(tr.fallback_steps!=41u||tr.fallback_trace_count!=32u||
    tr.fallback_trace_pcs[0]!=0x1024u||
    tr.fallback_trace_pcs[31]!=0x10a0u||
    tr.fallback_trace_words[31]!=UINT32_C(0x4e800020))return 17;
 ar_lv2_bootstrap_reset();
 if(ar_lv2_current_time_queries()!=0u)return 18;
 ar_bridge_shutdown();
 puts("M7.30 native MFCR full CR, real LV2 145 guest BE sec/nsec, fail-closed and fallback trace PASS");
 return 0;
}
