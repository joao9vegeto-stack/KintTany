/* M7.67 test ACTUAL AOT dispatcher and PRX-bound HLE with no fallback. */
#include "ppu_bridge.h"
#include <stdio.h>
#include <string.h>
static int returns_unresolved(ppu_context*c){c->cia=UINT64_C(0x00669a84);c->lr=UINT64_C(0x0053950c);c->gpr[2]=0;return AR_UNRESOLVED;}
static int native_to_import(ppu_context*c){c->cia=UINT64_C(0x00669a84);c->lr=UINT64_C(0x0053950c);return AR_TAIL;}
static int genuine_mock_hle(ppu_context*c){c->gpr[3]=0;return AR_OK;}
int main(void){
 ppu_context c;ar_aot_trace t;memset(&c,0,sizeof(c));
 if(ar_bridge_init(4096u)!=AR_OK)return 1;
 if(ar_register(0x005394e8u,returns_unresolved)!=AR_OK)return 2;
 if(ar_run(&c,0x005394e8u,8u)!=AR_UNRESOLVED)return 3;
 ar_trace_snapshot(&t);
 if(t.unresolved_pc!=0x00669a84u||t.m767_fail_pc!=0x00669a84u||
    t.m767_fail_reason!=2u||t.m767_failed_handler_pc!=0x005394e8u||
    t.stop_lr!=0x0053950cu)return 4;
 if(ar_register(0x005394ecu,native_to_import)!=AR_OK)return 5;
 if(ar_bind_import(0x00669a84u,0x2f85c0efu)!=AR_OK||
    ar_bind_hle(0x2f85c0efu,genuine_mock_hle)!=AR_OK)return 6;
 memset(&c,0,sizeof(c));c.gpr[2]=0x83f2b0u;c.gpr[3]=0x1000u;
 if(ar_run(&c,0x005394ecu,8u)!=AR_OK)return 7;
 ar_trace_snapshot(&t);
 if(t.m767_hle_stub!=0x00669a84u||t.m767_hle_nid!=0x2f85c0efu||
    t.m767_hle_calls!=1u||t.m767_hle_success!=1u||
    t.m767_hle_pre_toc!=0x83f2b0u||t.m767_hle_pre_r3!=0x1000u||
    t.m767_hle_post_r3!=0u||c.gpr[2]!=0x83f2b0u||
    c.lr!=0x0053950cu)return 8;
 ar_bridge_shutdown();
 puts("M7.67 live AOT fail PC and authenticated import HLE tracking PASS");
 return 0;
}
