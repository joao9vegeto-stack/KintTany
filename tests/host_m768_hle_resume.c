/* M7.68 PPC->native HLE resume, missing LR and nested direct HLE test. */
#include "ppu_bridge.h"
#include <stdio.h>
#include <string.h>
static int hit;
static int bl(ppu_context*c){c->lr=0x0053950cu;c->cia=0x00669a84u;return AR_TAIL;}
static int exit_ok(ppu_context*c){hit++;c->gpr[7]=0xbeefu;return AR_OK;}
static int fake_hle(ppu_context*c){c->gpr[3]=0;return AR_OK;}
static int direct_nested(ppu_context*c){
 int rc=ar_guest_call(c,0x00669a84u);
 if(rc!=AR_OK)return rc;
 c->gpr[8]=0xabcdefu;return AR_OK;
}
static int invalid_lr(ppu_context*c){c->lr=0x00539520u;c->cia=0x00669a84u;return AR_TAIL;}
int main(void){
 ppu_context c;ar_aot_trace t;memset(&c,0,sizeof(c));
 if(ar_bridge_init(4096)!=AR_OK)return 1;
 if(ar_register(0x005394e8,bl)!=AR_OK||
    ar_register(0x0053950c,exit_ok)!=AR_OK||
    ar_register(0x00539510,direct_nested)!=AR_OK||
    ar_register(0x00539514,invalid_lr)!=AR_OK||
    ar_bind_import(0x00669a84,0x2f85c0ef)!=AR_OK||
    ar_bind_hle(0x2f85c0ef,fake_hle)!=AR_OK)return 2;
 c.cr=0x22000044u;c.lr=0x10858u;c.gpr[2]=0x83f2b0u;c.gpr[3]=0x1234u;
 if(ar_run(&c,0x005394e8,8)!=AR_OK||hit!=1||c.gpr[7]!=0xbeefu||
    c.lr!=0x0053950cu||c.gpr[2]!=0x83f2b0u||c.cr!=0x22000044u)return 3;
 ar_trace_snapshot(&t);
 if(t.m768_tail_hle_lookup_count!=1||t.m768_tail_hle_found_count!=1||
    t.m768_last_hle_return_pc!=0x53950cu||
    t.m768_hle_return_native!=1||t.m768_hle_return_count!=1||
    t.m767_hle_success!=1||t.unique_aot!=2||t.fallback_steps)return 4;
 memset(&c,0,sizeof(c));c.lr=0x0053950cu;c.gpr[2]=0x83f2b0u;
 if(ar_run(&c,0x00539510u,8u)!=AR_OK ||c.gpr[8]!=0xabcdefu||hit!=1)return 5;
 ar_trace_snapshot(&t);
 if(t.m768_hle_return_count!=0||t.m768_last_hle_entry_from_tail!=0||
    t.m767_hle_success!=1)return 6;
 memset(&c,0,sizeof(c));c.gpr[2]=0x83f2b0u;
 if(ar_run(&c,0x00539514u,8u)!=AR_UNRESOLVED)return 7;
 ar_trace_snapshot(&t);
 if(t.unresolved_pc!=0x00539520u||t.m767_fail_pc!=0x00539520u||
    t.m767_fail_reason!=1u||t.m768_hle_return_count!=1u||
    t.m768_hle_return_native!=0u||t.fallback_steps!=0u)return 8;
 ar_bridge_shutdown();
 puts("M7.68 PPC native BL->HLE->LR native resume, nested call, fail-closed PASS");
 return 0;
}
