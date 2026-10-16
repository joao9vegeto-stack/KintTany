/* M7.8 synthetic native syscall and time service ABI, no PS3 game. */
#include <stdio.h>
#include <stdint.h>
#include "ppu_bridge.h"
#include "ppu_lv2_bootstrap.h"
int main(void){
 ppu_context c; ppu_context_init(&c);
 if(ar_bridge_init(0x40000u)!=AR_OK)return 1;
 ar_lv2_bootstrap_reset();
 if(ar_bind_syscall(0x160u,ar_lv2_user_memory_size)!=AR_OK ||
    ar_bind_import(0x10080u,0x8461e528u)!=AR_OK ||
    ar_bind_hle(0x8461e528u,ar_lv2_system_time)!=AR_OK)return 2;
 /* Native test code must invoke real dispatcher (which sets depth). */
 extern int m78_entry(ppu_context*);
 if(ar_register(0x10000u,m78_entry)!=AR_OK)return 3;
 c.lr=0x10010u;c.gpr[3]=0x30000u;
 if(ar_run(&c,0x10000u,20u)!=AR_OK||
    c.gpr[3]==0u||
    ar_lv2_user_memory_queries()!=1u ||
    ar_lv2_time_queries()!=1u ||
    ar_read32(0x30000u)!=0x10000000u ||
    ar_read32(0x30004u)!=0x0e000000u ||
    ar_last_error()!=AR_OK)return 4;
 ar_bridge_shutdown();
 puts("M7.8 genuine native AOT LV2 memory/time guest ABI PASS");
 return 0;
}
int m78_entry(ppu_context*c){
 uint64_t saved_lr=c->lr;
 c->gpr[3]=0x30000u;
 c->gpr[11]=0x160u;
 int rc=ar_guest_syscall(c);
 if(rc)return rc;
 if(c->gpr[3]!=0u)return AR_BAD_ARGS;
 c->lr=saved_lr;
 return ar_guest_call(c,0x10080u);
}
