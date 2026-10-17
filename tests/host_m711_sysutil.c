#include "ppu_native_sysutil.h"
#include <stdio.h>
static int native_entry(ppu_context*c){
 c->gpr[3]=0x15u;
 if(ar_guest_call(c,0x10080u)!=AR_OK||c->gpr[3])return AR_BAD_ARGS;
 c->gpr[3]=0x111;c->gpr[4]=0x20000;
 if(ar_guest_call(c,0x10090)!=AR_OK||
    c->gpr[3]||ar_read32(0x20000)!=1u)return AR_BAD_ARGS;
 c->gpr[3]=2;c->gpr[4]=0x10500;c->gpr[5]=0x20200;
 if(ar_guest_call(c,0x100a0)!=AR_OK||c->gpr[3])return AR_BAD_ARGS;
 if(ar_guest_call(c,0x100b0)!=AR_OK||c->gpr[3])return AR_BAD_ARGS;
 c->gpr[3]=2;
 if(ar_guest_call(c,0x100c0)!=AR_OK||c->gpr[3])return AR_BAD_ARGS;
 return AR_OK;
}
int main(void){
 ppu_context c;ppu_context_init(&c);
 if(ar_bridge_init(0x30000)!=AR_OK)return 1;
 ar_sysutil_reset();c.gpr[3]=0x15;
 if(ar_sysutil_load_module(&c)!=AR_MISSING_HLE)return 2;
 const uint32_t nid[]={0x189a74da,0x9d98afa0,0x02ff3c1b,0x40e895d3};
 const uint32_t stub[]={0x100b0,0x100a0,0x100c0,0x10090};
 for(unsigned i=0;i<4;i++)if(ar_sysutil_bind_core(nid[i],stub[i])!=AR_OK)return 3;
 if(ar_bind_import(0x10080,0x32267a31u)!=AR_OK||
    ar_bind_hle(0x32267a31u,ar_sysutil_load_module)!=AR_OK||
    ar_register(0x10000,native_entry)!=AR_OK)return 4;
 if(ar_run(&c,0x10000,32)!=AR_OK||!ar_sysutil_is_native_ready())return 5;
 ar_bridge_shutdown();
 puts("M7.11 native SYSUTIL core and fail-closed module load PASS");
 return 0;
}
