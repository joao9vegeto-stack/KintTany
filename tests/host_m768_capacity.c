/* M7.68 structural scale limit: 29,849 native AOT entries, no PPC fallback. */
#include "ppu_bridge.h"
#include <stdio.h>
#include <string.h>
static int native(ppu_context*c){c->gpr[3]=0x768u;return AR_OK;}
int main(void){
 const unsigned base=0x10000u,count=29849u;
 if(ar_bridge_init(4096)!=AR_OK)return 1;
 for(unsigned i=0;i<count;i++)
    if(ar_register(base+4u*i,native)!=AR_OK)return 2;
 if(ar_registered_count()!=count)return 3;
 if(ar_register(base+4u*(count-1),native)!=AR_DUPLICATE)return 4;
 ppu_context c;memset(&c,0,sizeof(c));
 if(ar_run(&c,base+4u*(count-1),6u)!=AR_OK ||c.gpr[3]!=0x768u)return 5;
 ar_aot_trace tr;ar_trace_snapshot(&tr);
 if(tr.unique_aot!=1||tr.aot_dispatches!=1||tr.fallback_steps!=0)return 6;
 ar_bridge_shutdown();
 puts("M7.68 native AOT registry 29849 synthetic entries and final dispatch PASS");
 return 0;
}
