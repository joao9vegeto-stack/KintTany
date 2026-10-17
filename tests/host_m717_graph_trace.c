/* M7.17 synthetic-only stress test of hash index, native trace and
 * bounded executable PPC control-flow graph. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_m717_graph.h"
static void w16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void w32(uint8_t*p,uint32_t x){p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;}
static void w64(uint8_t*p,uint64_t x){w32(p,(uint32_t)(x>>32));w32(p+4,(uint32_t)x);}
static int tail(ppu_context*c){c->cia+=4u;return AR_TAIL;}
static int done(ppu_context*c){c->gpr[0]++;return AR_OK;}
int main(void) {
 if(ar_bridge_init(0x4000)!=AR_OK)return 1;
 if(ar_register(0x2000,tail)!=AR_OK||ar_register(0x2004,tail)!=AR_OK||
    ar_register(0x2008,done)!=AR_OK)return 2;
 for(unsigned i=0;i<3000;i++)
   if(ar_register(0x10000000u+i*0x1000u,done)!=AR_OK)return 3;
 if(ar_registered_count()!=3003u||
    ar_register(0x2008,done)!=AR_DUPLICATE ||
    ar_register(0x2001,done)!=AR_BAD_ARGS)return 4;
 ppu_context c={0};c.cia=0x2000;
 if(ar_run(&c,0x2000,16)!=AR_OK||c.gpr[0]!=1)return 5;
 ar_aot_trace tr={0};ar_trace_snapshot(&tr);
 if(tr.aot_dispatches!=3u||tr.unique_aot!=3u||tr.unresolved_pc!=0u||
    tr.trace_count!=3u||tr.max_budget!=16u||tr.trace_pcs[0]!=0x2000u||
    tr.trace_pcs[1]!=0x2004u||tr.trace_pcs[2]!=0x2008u)return 6;
 c.cia=0x2000;
 if(ar_run(&c,0x2000,2)!=AR_BUDGET)return 7;
 ar_trace_snapshot(&tr);
 if(tr.aot_dispatches!=2||tr.unique_aot!=2||tr.trace_count!=2)return 8;
 if(ar_run(&c,0x3000,16)!=AR_UNRESOLVED||ar_last_unresolved()!=0x3000)return 9;
 ar_trace_snapshot(&tr);
 if(tr.unresolved_pc!=0x3000||tr.aot_dispatches!=0||tr.trace_count!=0)return 10;
 if(ar_run(&c,0x10000000u+1234u*0x1000u,4)!=AR_OK)return 11;
 ar_trace_snapshot(&tr);
 if(tr.aot_dispatches!=1||tr.unique_aot!=1||
    tr.trace_pcs[0]!=(0x10000000u+1234u*0x1000u))return 12;
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 w16(elf+16,2);w16(elf+18,21);w32(elf+20,1);
 w64(elf+32,64);w16(elf+54,56);w16(elf+56,1);
 uint8_t*ph=elf+64;w32(ph,1);w32(ph+4,5);w64(ph+8,0x200);
 w64(ph+16,0x1000);w64(ph+32,0x120);w64(ph+40,0x120);
 for(unsigned i=0;i<0x120/4;i++)w32(elf+0x200u+4u*i,0x4e800020u);
 w32(elf+0x200,0x48000101u); /* BL +0x100 = 0x1100 */
 w32(elf+0x204,0x4182000cu); /* BC +0xC = 0x1010 */
 w32(elf+0x210,0x48000020u); /* B +0x20 = 0x1030 */
 uint32_t root=0x1000;ar_m717_graph gr={0};
 if(ar_m717_walk(elf,sizeof(elf),&root,1,64,&gr)!=0)return 13;
 if(gr.inspected!=6u||gr.direct_calls!=1u||gr.conditional!=1u||
    gr.call_count!=1u||gr.calls[0]!=0x1100u||gr.indirect!=3u||
    gr.saturated!=0u)return 14;
 if(ar_m717_walk(elf,sizeof(elf),&root,1,2,&gr)!=0||
    gr.inspected!=2u||gr.saturated!=1u)return 15;
 w32(ph+4,4);
 if(ar_m717_walk(elf,sizeof(elf),&root,1,64,&gr)!=0||
    gr.inspected!=0u||gr.invalid_pc==0u)return 16;
 ar_bridge_shutdown();
 ar_trace_snapshot(&tr);
 if(tr.aot_dispatches||tr.trace_count)return 17;
 puts("M7.17 bounded PPC graph, 3000-entry hashed ARM64 index and real AOT trace PASS");
 return 0;
}
