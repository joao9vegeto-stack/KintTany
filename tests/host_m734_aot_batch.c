/* M7.34 bulk AOT regression. All PPC contexts and ELF payload synthetic.
 * Proves the observed control-flow chain crosses *multiple* native entries
 * with zero interpreted instructions. No claim this proves game boot.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m734_native_0052a9a0(ppu_context*);
extern int ar_m734_native_0052a9dc(ppu_context*);
extern int ar_m734_native_0052aa18(ppu_context*);
extern int ar_m734_native_0052aa90(ppu_context*);
extern int ar_m734_native_0052aa94(ppu_context*);
extern int ar_m734_native_0052a910(ppu_context*);
extern int ar_m734_native_0052aa1c(ppu_context*);
extern int ar_m734_native_0052aaa0(ppu_context*);
extern int ar_m734_register_batch(const uint8_t*,size_t);
static int end(ppu_context *c){c->cia=c->lr;return AR_OK;}
static void b16(uint8_t*b,uint16_t v){b[0]=v>>8;b[1]=(uint8_t)v;}
static void b32(uint8_t*b,uint32_t v){
 b[0]=v>>24;b[1]=v>>16;b[2]=v>>8;b[3]=(uint8_t)v;
}
static void b64(uint8_t*b,uint64_t v){
 b32(b,(uint32_t)(v>>32));b32(b+4,(uint32_t)v);
}
int main(void){
 if(ar_bridge_init(0x600000u)!=AR_OK)return 1;
 const struct {uint32_t pc;ar_ppu_fn fn;} functions[]={
  {0x0052a9a0,ar_m734_native_0052a9a0},
  {0x0052a9dc,ar_m734_native_0052a9dc},
  {0x0052aa18,ar_m734_native_0052aa18},
  {0x0052aa1c,ar_m734_native_0052aa1c},
  {0x0052aa90,ar_m734_native_0052aa90},
  {0x0052aa94,ar_m734_native_0052aa94},
  {0x0052a910,ar_m734_native_0052a910},
  {0x0052aaa0,ar_m734_native_0052aaa0},
  {0x0052a960,end},{0x0052a928,end},{0x0052aab0,end}
 };
 for(size_t i=0;i<sizeof(functions)/sizeof(functions[0]);i++){
   if(ar_register(functions[i].pc,functions[i].fn)!=AR_OK)return 2;
 }
 ppu_context c={0};c.lr=UINT32_C(0x00524000);
 c.gpr[1]=UINT64_C(0x7000);c.gpr[3]=UINT64_C(0x5000);
 c.gpr[4]=UINT64_C(5);c.gpr[5]=0;
 c.gpr[27]=UINT64_C(0x7fffffffffffffff);
 c.gpr[28]=UINT64_C(0x6000);
 c.xer=UINT32_C(0xc0000000);c.cr=UINT32_C(0x76543210);
 /* AOT a9a0 -> a9dc -> aa18 -> aa1c -> aa94 -> a910
  * -> a928 (stub return) -> aaa0 -> aab0 (stub final). */
 if(ar_run(&c,0x0052a9a0,128u)!=AR_OK)return 3;
 ar_aot_trace trace={0};ar_trace_snapshot(&trace);
 if(trace.fallback_steps||trace.aot_dispatches!=9u||
    trace.unique_aot!=9u||trace.trace_count!=9u||
    trace.trace_pcs[0]!=UINT32_C(0x0052a9a0)||
    trace.trace_pcs[1]!=UINT32_C(0x0052a9dc)||
    trace.trace_pcs[2]!=UINT32_C(0x0052aa18)||
    trace.trace_pcs[3]!=UINT32_C(0x0052aa1c)||
    trace.trace_pcs[4]!=UINT32_C(0x0052aa94)||
    trace.trace_pcs[5]!=UINT32_C(0x0052a910)||
    trace.trace_pcs[6]!=UINT32_C(0x0052a928)||
    trace.trace_pcs[7]!=UINT32_C(0x0052aaa0)||
    trace.trace_pcs[8]!=UINT32_C(0x0052aab0))return 4;
 if(c.gpr[1]!=UINT64_C(0x7000-176) ||
    ar_read64(c.gpr[1])!=UINT64_C(0x7000) ||
    ar_read64(c.gpr[1]+192)!=UINT32_C(0x00524000) ||
    ar_read32(0x5020)!=0u ||
    c.gpr[4]!=0u ||c.gpr[10]!=4u ||ar_read32(0x5018u)!=4u)return 5;
 /* Mismatching ELF 100% fails validation. No commercial bytes in test. */
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 b16(elf+16,2);b16(elf+18,21);b32(elf+20,1);
 b64(elf+32,64);b16(elf+54,56);b16(elf+56,1);
 uint8_t*ph=elf+64;b32(ph,1);b32(ph+4,5);
 b64(ph+8,0x200);b64(ph+16,0x0052a910);
 b64(ph+32,256);b64(ph+40,256);
 for(unsigned i=0;i<64;i++)b32(elf+0x200+i*4u,0x60000000u);
 if(ar_vm_load(0x0052a910,elf+0x200,256)!=AR_OK)return 6;
 if(ar_m734_register_batch(elf,sizeof(elf))!=AR_BAD_ARGS)return 7;
 ar_bridge_shutdown();
 puts("M7.34 batch AOT guest chain: 9 native dispatches, 0 PPC fallback, strict ELF fail-closed PASS");
 return 0;
}
