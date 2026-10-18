/* M7.55: native AOT-only, fail-closed C runtime. Synthetic guest code. */
#include <stdint.h>
#include <stdio.h>
#include "ppu_bridge.h"
static int native_entry(ppu_context*c){c->cia=UINT32_C(0x00010420);return AR_TAIL;}
static int legacy_eval(ppu_context*c,const uint8_t*elf,size_t len,uint32_t pc,uint32_t*out){
 (void)c;(void)elf;(void)len;(void)pc;
 if(out)*out=0x60000000;
 return AR_TAIL;
}
int main(void){
 uint8_t elf[64]={0};
 if(ar_bridge_init(65536u)!=AR_OK)return 1;
 if(ar_register(0x00010410u,native_entry)!=AR_OK)return 2;
 if(ar_ppc_fallback_attach(elf,sizeof(elf),16384u,legacy_eval)!=AR_BAD_ARGS)return 3;
 ppu_context c={0};
 const int rc=ar_run(&c,0x00010410u,128u);
 ar_aot_trace t={0};ar_trace_snapshot(&t);
 if(rc!=AR_UNRESOLVED||ar_last_unresolved()!=0x00010420u ||
    t.aot_dispatches!=1u||t.unique_aot!=1u ||
    t.fallback_steps!=0u||t.fallback_trace_count!=0u ||
    t.unresolved_pc!=0x00010420u)return 4;
 ar_bridge_shutdown();
 puts("M7.55 AOT ONLY: no PPC interpreter attachment, 1 native AOT dispatch, missing PC fail-closed, fallback=0 PASS");
 return 0;
}
