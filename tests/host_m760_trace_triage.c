/* Native-only runtime flight recorder; synthetic PCs, no guest ELF or asset. */
#include <stdint.h>
#include <stdio.h>
#include "ppu_bridge.h"
static uint32_t count;
static int busy(ppu_context*c){
 count++;
 c->cia=count<100u?0x00010410u:0x00010420u;
 return AR_TAIL;
}
static int continue_to_missing(ppu_context*c){
 c->cr=0x12345678u;c->xer=0xA0000000u;
 c->lr=0x10500u;c->ctr=0x10600u;
 c->gpr[1]=0x220000u;c->gpr[2]=0x330000u;c->gpr[3]=0x440000u;
 c->cia=0x00010430u;
 return AR_TAIL;
}
int main(void){
 if(ar_bridge_init(65536u)!=AR_OK)return 1;
 if(ar_register(0x00010410u,busy)!=AR_OK ||
    ar_register(0x00010420u,continue_to_missing)!=AR_OK)return 2;
 ppu_context c={0};
 if(ar_run(&c,0x00010410u,200u)!=AR_UNRESOLVED)return 3;
 ar_aot_trace t={0};ar_trace_snapshot(&t);
 if(t.aot_dispatches!=101u||t.unique_aot!=2u||
    t.unresolved_pc!=0x00010430u||t.fallback_steps!=0u)return 4;
 if(t.first_total!=2u||t.first_count!=2u||
    t.first_pcs[0]!=0x00010410u||t.first_pcs[1]!=0x00010420u)return 5;
 if(t.run_total!=2u||t.run_count!=2u||
    t.run_pcs[0]!=0x00010410u||t.run_repetitions[0]!=100u||
    t.run_pcs[1]!=0x00010420u||t.run_repetitions[1]!=1u)return 6;
 if(t.stop_previous_aot!=0x00010420u||t.stop_cr!=0x12345678u||
    t.stop_xer!=0xA0000000u||t.stop_lr!=0x10500u||
    t.stop_ctr!=0x10600u||t.stop_r1!=0x220000u||
    t.stop_r2!=0x330000u||t.stop_r3!=0x440000u)return 7;
 count=0;
 if(ar_run(&c,0x00010410u,200u)!=AR_UNRESOLVED)return 8;
 ar_trace_snapshot(&t);
 if(t.run_count!=2||t.first_count!=2||t.run_repetitions[0]!=100u)return 9;
 ar_bridge_shutdown();
 puts("M7.60 AOT flight recorder: 100 hot-loop dispatches -> one RLE run; exact first visits, stop predecessor and registers; reset verified PASS");
 return 0;
}
