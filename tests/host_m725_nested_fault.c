/* M7.25: synthetic nested BLs must preserve the actual faulting
 * instruction, rather than overwriting it with the BL caller PC.
 * Also validates SRAWI arithmetic word shifts and XER.CA with UBSan.
 * No original commercial PPC, game ELF or game assets included.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
static void be16(uint8_t*p,uint16_t n){p[0]=(uint8_t)(n>>8);p[1]=(uint8_t)n;}
static void be32(uint8_t*p,uint32_t n){
 p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);
 p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n;
}
static void be64(uint8_t*p,uint64_t n){be32(p,(uint32_t)(n>>32));be32(p+4,(uint32_t)n);}
static uint32_t srawi(unsigned rs,unsigned ra,unsigned sh,unsigned rc){
 return (31u<<26)|(rs<<21)|(ra<<16)|(sh<<11)|(824u<<1)|rc;
}
static int step(uint8_t *elf,ppu_context*c,uint32_t word){
 be32(elf+0x200,word);
 if(ar_vm_load(0x1000,elf+0x200,4)!=AR_OK)return -98;
 uint32_t observed=0;
 const int rc=ar_ppc_fallback_step(c,elf,1024,0x1000,&observed);
 return observed==word?rc:-99;
}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
 be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t *ph=elf+64;
 be32(ph,1);be32(ph+4,5);be64(ph+8,0x200);
 be64(ph+16,0x1000);be64(ph+32,0x100);be64(ph+40,0x100);
 /* 0x1000 BL -> 0x1020, 0x1020 BL -> 0x1040, 0x1040 unknown */
 be32(elf+0x200,UINT32_C(0x48000021));
 be32(elf+0x220,UINT32_C(0x48000021));
 be32(elf+0x240,UINT32_C(0xffffffff));
 if(ar_bridge_init(0x4000)!=AR_OK)return 1;
 if(ar_vm_load(0x1000,elf+0x200,0x100)!=AR_OK)return 2;
 if(ar_ppc_fallback_attach(elf,1024,64,ar_ppc_fallback_step)!=AR_OK)return 3;
 ppu_context ctx={0};
 if(ar_run(&ctx,0x1000,64)!=AR_PPC_UNSUPPORTED)return 4;
 ar_aot_trace tr={0};ar_trace_snapshot(&tr);
 if(ar_last_unresolved()!=0x1040u||tr.unresolved_pc!=0x1040u||
    tr.fallback_unsupported_pc!=0x1040u||
    tr.fallback_unsupported_word!=UINT32_C(0xffffffff)||
    tr.fallback_callsite_pc!=0x1020u||tr.fallback_call_target!=0x1040u)
    return 5;
 /* A new ar_run resets both the failed PC and its call edge. */
 be32(elf+0x200,UINT32_C(0xffffffff));
 if(ar_vm_load(0x1000,elf+0x200,4)!=AR_OK)return 6;
 memset(&ctx,0,sizeof(ctx));
 if(ar_run(&ctx,0x1000,64)!=AR_PPC_UNSUPPORTED)return 7;
 ar_trace_snapshot(&tr);
 if(tr.fallback_callsite_pc!=0u||tr.fallback_call_target!=0u||
    tr.fallback_unsupported_pc!=0x1000u)return 8;
 /* ar_run intentionally retains error state until a fresh VM session. */
 ar_bridge_shutdown();
 if(ar_bridge_init(0x4000)!=AR_OK)return 12;
 /* 32-bit arithmetic shift, PPC64 sign extension, sticky SO and CR0. */
 memset(&ctx,0,sizeof(ctx));
 ctx.gpr[3]=UINT64_C(0xfffffffd);
 ctx.xer=UINT32_C(0x80000000);
 ctx.cr=UINT32_C(0x000000ab);
 if(step(elf,&ctx,srawi(3,4,1,1))!=AR_TAIL||
    ctx.gpr[4]!=UINT64_C(0xfffffffffffffffe)||
    ctx.xer!=UINT32_C(0xa0000000)||
    ctx.cr!=UINT32_C(0x900000ab))return 9;
 ctx.gpr[3]=UINT64_C(0xfffffffc);
 if(step(elf,&ctx,srawi(3,4,1,1))!=AR_TAIL||
    ctx.gpr[4]!=UINT64_C(0xfffffffffffffffe)||
    ctx.xer!=UINT32_C(0x80000000))return 10;
 ctx.gpr[3]=UINT64_C(0xffffffff);
 if(step(elf,&ctx,srawi(3,3,0,0))!=AR_TAIL||
    ctx.gpr[3]!=UINT64_MAX||
    ctx.xer!=UINT32_C(0x80000000))return 11;
 ar_bridge_shutdown();
 puts("M7.25 deep PPC BL fault origin + SRAWI signed carry and CR0 PASS");
 return 0;
}
