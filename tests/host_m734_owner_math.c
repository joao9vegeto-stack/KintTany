/* M7.34 native 29-instruction arithmetic block: four independent
 * expected-value oracles including INT64 extremes. Only synthetic VM.
 * The original commercial ELF/instruction stream is never checked in.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m734_native_0052aa1c(ppu_context*);
extern int ar_m734_register_block(const uint8_t*,size_t);
#define START UINT32_C(0x0052aa1c)
#define END UINT32_C(0x0052aa94)
static int halt(ppu_context*c){c->cia=c->lr;return AR_OK;}
static void p16(uint8_t*p,uint16_t v){p[0]=v>>8;p[1]=(uint8_t)v;}
static void p32(uint8_t*p,uint32_t v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=(uint8_t)v;}
static void p64(uint8_t*p,uint64_t v){p32(p,(uint32_t)(v>>32));p32(p+4,(uint32_t)v);}
typedef struct {
 uint64_t source,r0,r10,r29,r30,r31;
 uint32_t carry;
} expectation;
static const expectation cases[]={
 {UINT64_C(123456789),UINT64_C(0x594),UINT64_C(1),
  UINT64_C(0x447),UINT64_C(0x594),UINT64_C(3),0u},
 {UINT64_C(0xfffffffff8a432eb),UINT64_C(0x00000000fffffa73),
  UINT64_C(0xfffffffefffffffa),UINT64_C(0xfffffffffffffbb9),
  UINT64_C(0xfffffffffffffa6c),UINT64_C(0xfffffffffffffffd),1u},
 {UINT64_C(0x8000000000000000),UINT64_C(0x00000000dd7cc6c0),
  UINT64_C(0xffff9ee7fffffffd),UINT64_C(0xffffffffdd7cc766),
  UINT64_C(0xffff9ee8dd7cc6bc),UINT64_C(0xffffffffffE7cb3e),1u},
 {UINT64_C(0x7fffffffffffffff),UINT64_C(0x0000000022833940),
  UINT64_C(0x0000611700000005),UINT64_C(0x000000002283389a),
  UINT64_C(0x0000611722833944),UINT64_C(0x00000000001834c2),0u},
 {UINT64_C(0),UINT64_C(0),UINT64_C(1),UINT64_C(0),
  UINT64_C(0),UINT64_C(0),0u}
};
int main(void){
 if(ar_bridge_init(0x600000u)!=AR_OK)return 1;
 if(ar_register(START,ar_m734_native_0052aa1c)!=AR_OK||
    ar_register(END,halt)!=AR_OK)return 2;
 for(size_t i=0;i<sizeof(cases)/sizeof(cases[0]);i++){
    const expectation*e=&cases[i];
    ppu_context cpu={0};
    cpu.gpr[27]=e->source;
    cpu.gpr[28]=0x4000u;
    cpu.gpr[0]=UINT64_C(0x18450000); /* preceding real LIS instruction */
    cpu.gpr[1]=0x5000u;cpu.cr=UINT32_C(0xabcde123);
    cpu.xer=UINT32_C(0xd0000000);cpu.lr=0x4100u;
    if(ar_run(&cpu,START,40u)!=AR_OK)return (int)(10+i);
    if(cpu.gpr[0]!=e->r0||cpu.gpr[10]!=e->r10||
       cpu.gpr[29]!=e->r29||cpu.gpr[30]!=e->r30||
       cpu.gpr[31]!=e->r31||
       cpu.gpr[26]!=(e->source>>63?UINT64_MAX:0u)||
       ((cpu.xer>>29)&1u)!=e->carry||
       (cpu.xer&UINT32_C(0xd0000000))!=UINT32_C(0xd0000000)||
       cpu.cr!=UINT32_C(0xabcde123)||cpu.gpr[1]!=0x5000u||
       cpu.gpr[27]!=e->source||cpu.gpr[28]!=0x4000u||
       ar_read32(0x4018u)!=(uint32_t)e->r10)
          return (int)(20+i);
    ar_aot_trace t={0};ar_trace_snapshot(&t);
    if(t.aot_dispatches!=2u||t.unique_aot!=2u||
       t.fallback_steps!=0u||t.trace_count!=2u||
       t.trace_pcs[0]!=START||t.trace_pcs[1]!=END)return (int)(30+i);
 }
 /* Reject fake ELF with NOP-only guest text: no owner bytes in test. */
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 p16(elf+16,2);p16(elf+18,21);p32(elf+20,1);
 p64(elf+32,64);p16(elf+54,56);p16(elf+56,1);
 uint8_t*ph=elf+64;p32(ph,1);p32(ph+4,5);
 p64(ph+8,0x200);p64(ph+16,START);
 p64(ph+32,116u);p64(ph+40,116u);
 for(unsigned k=0;k<29u;k++)p32(elf+0x200+4u*k,UINT32_C(0x60000000));
 if(ar_vm_load(START,elf+0x200,116u)!=AR_OK)return 40;
 if(ar_m734_register_block(elf,sizeof(elf))!=AR_BAD_ARGS||
    ar_registered_count()!=2u)return 41;
 p32(ph+4,4u); /* no PT_LOAD X */
 if(ar_m734_register_block(elf,sizeof(elf))!=AR_BAD_ARGS)return 42;
 /* XS SRADI fallback must interpret the SH high bit correctly (63). */
 const uint32_t sradi=UINT32_C(0x7f7afe76);
 p32(elf+0x200,sradi);p32(ph+4,5u);
 if(ar_vm_load(START,elf+0x200,4u)!=AR_OK)return 43;
 ppu_context one={0};one.gpr[27]=UINT64_C(0xfffffffffffffff5);
 one.xer=UINT32_C(0x90000000);
 uint32_t seen=0;
 if(ar_ppc_fallback_step(&one,elf,sizeof(elf),START,&seen)!=AR_TAIL ||
    seen!=sradi||one.gpr[26]!=UINT64_MAX||
    !(one.xer&UINT32_C(0x20000000))||
    (one.xer&UINT32_C(0x90000000))!=UINT32_C(0x90000000))return 44;
 ar_bridge_shutdown();
 puts("M7.34 29 owner instructions natively translated: 5 signed oracles, 2 dispatches 0 fallback, SRADI63 and strict ELF checks PASS");
 return 0;
}
