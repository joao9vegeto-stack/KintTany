/* Actual native dispatcher must report AOT_TAIL source/destination/handler. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
static int known(ppu_context*c){c->cia=UINT64_C(0x2000);return AR_TAIL;}
static int target(ppu_context*c){c->gpr[3]=42u;return AR_OK;}
static int unknown(ppu_context*c){c->cia=UINT64_C(0x3000);return AR_TAIL;}
int main(void){
 ppu_context c;ar_aot_trace t;
 memset(&c,0,sizeof(c));
 if(ar_bridge_init(4096u)!=AR_OK)return 1;
 if(ar_register(0x1000u,known)!=AR_OK||ar_register(0x2000u,target)!=AR_OK||
    ar_register(0x1004u,unknown)!=AR_OK)return 2;
 if(ar_run(&c,0x1000u,32u)!=AR_OK||c.gpr[3]!=42u)return 3;
 ar_trace_snapshot(&t);
 if(t.tail_count!=1u||t.tail_source!=0x1000u||t.tail_target!=0x2000u||
    t.tail_target_has_native!=1u||t.first_unlinked_tail_target!=0u)return 4;
 if(ar_run(&c,0x1004u,32u)!=AR_UNRESOLVED)return 5;
 ar_trace_snapshot(&t);
 if(t.tail_count!=1u||t.tail_source!=0x1004u||t.tail_target!=0x3000u||
    t.tail_target_has_native||t.first_unlinked_tail_source!=0x1004u||
    t.first_unlinked_tail_target!=0x3000u)return 6;
 ar_bridge_shutdown();
 puts("M7.64.1 real dispatcher AOT_TAIL source target handler and unresolved PASS");
 return 0;
}
