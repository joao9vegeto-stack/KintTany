/* M7.27: only synthetic PPC/BE ELF. No user assets, secrets or code.
 * Demonstrates ordered guest stores and authentic barrier instructions,
 * rejects invalid/privileged forms, and reports executed fallback counts.
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
static uint32_t stw(unsigned rs,unsigned ra,unsigned off){
 return (36u<<26)|(rs<<21)|(ra<<16)|(off&0xffffu);
}
static int load_words(uint8_t*elf,const uint32_t*words,size_t count){
 for(size_t i=0;i<count;i++)be32(elf+0x200+i*4,words[i]);
 return ar_vm_load(0x1000,elf+0x200,count*4);
}
static int run(ppu_context*c){return ar_run(c,0x1000,32);}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
 be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t*ph=elf+64;be32(ph,1);be32(ph+4,5);
 be64(ph+8,0x200);be64(ph+16,0x1000);
 be64(ph+32,0x100);be64(ph+40,0x100);
 if(ar_bridge_init(0x3000)!=AR_OK)return 1;
 if(ar_ppc_fallback_attach(elf,sizeof(elf),64,ar_ppc_fallback_step)!=AR_OK)return 2;
 const uint32_t words[]={
  stw(18,31,0),UINT32_C(0x7c0006ac),
  stw(18,31,4),UINT32_C(0x7c0006ac),
  UINT32_C(0x4e800020)
 };
 if(load_words(elf,words,5)!=AR_OK)return 3;
 ppu_context c={0};c.gpr[31]=0x1800;c.gpr[18]=UINT64_C(0xaabbccdd);
 c.lr=0x1100;c.cr=UINT32_C(0xaabbccdd);c.xer=UINT32_C(0xa0000000);
 if(run(&c)!=AR_OK||c.cia!=0x1100u||
    ar_read32(0x1800)!=UINT32_C(0xaabbccdd)||
    ar_read32(0x1804)!=UINT32_C(0xaabbccdd)||
    c.cr!=UINT32_C(0xaabbccdd)||c.xer!=UINT32_C(0xa0000000))
    return 4;
 ar_aot_trace tr={0};ar_trace_snapshot(&tr);
 if(tr.eieio_steps!=2||tr.last_barrier_pc!=0x100cu||
    tr.fallback_steps!=5||tr.aot_dispatches!=0||
    tr.fallback_unsupported_pc!=0)return 5;
 const uint32_t sync_words[]={
  UINT32_C(0x7c0004ac),UINT32_C(0x7c2004ac),
  UINT32_C(0x4c00012c),UINT32_C(0x4e800020)
 };
 if(load_words(elf,sync_words,4)!=AR_OK)return 6;
 memset(&c,0,sizeof(c));c.lr=0x1100;c.gpr[11]=14;
 c.cr=UINT32_C(0x11223344);c.xer=UINT32_C(0xe0000000);
 if(run(&c)!=AR_OK||c.cr!=UINT32_C(0x11223344)||
    c.xer!=UINT32_C(0xe0000000)||c.gpr[11]!=14u)return 7;
 ar_trace_snapshot(&tr);
 if(tr.eieio_steps!=0||tr.sync_steps!=1||tr.lwsync_steps!=1||
    tr.isync_steps!=1||tr.last_barrier_pc!=0x1008u||
    tr.fallback_steps!=4)return 8;
 const uint32_t invalid[]={
  UINT32_C(0x7c2006ac),UINT32_C(0x7c0006ad),
  UINT32_C(0x7c4004ac),UINT32_C(0x4c20012c),
  UINT32_C(0xffffffff)
 };
 for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++){
   if(load_words(elf,&invalid[i],1)!=AR_OK)return 9;
   memset(&c,0,sizeof(c));c.lr=0x1100;c.gpr[3]=99;
   if(run(&c)!=AR_PPC_UNSUPPORTED)return 10;
   ar_trace_snapshot(&tr);
   if(ar_last_unresolved()!=0x1000u ||
      tr.fallback_unsupported_word!=invalid[i]||
      tr.fallback_unsupported_pc!=0x1000u ||
      tr.eieio_steps||tr.sync_steps||tr.lwsync_steps||tr.isync_steps||
      c.gpr[3]!=99u)return 11;
 }
 /* Guest code mutated away from the authenticated ELF must not execute. */
 const uint32_t verified=UINT32_C(0x7c0006ac),different=UINT32_C(0x7c0004ac);
 be32(elf+0x200,verified);
 uint8_t temp[4];be32(temp,different);
 if(ar_vm_load(0x1000,temp,4)!=AR_OK)return 12;
 memset(&c,0,sizeof(c));c.lr=0x1100;
 if(run(&c)!=AR_PPC_UNSUPPORTED)return 13;
 ar_trace_snapshot(&tr);
 if(tr.eieio_steps||tr.fallback_unsupported_pc!=0x1000u)return 14;
 ar_bridge_shutdown();
 puts("M7.27 PPC memory barriers EIEIO SYNC LWSYNC ISYNC ordered stores, native semantics, fail-closed PASS");
 return 0;
}
