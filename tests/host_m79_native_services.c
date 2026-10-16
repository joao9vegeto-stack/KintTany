/* Native signed guest bootstrap service ABI test — synthetic PS3 memory.
 * Exercises create, thread get-id, recursive fast lock and unlock.
 * Does not interpret any PowerPC guest instruction. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_lwmutex.h"
#include "ppu_lv2_bootstrap.h"
static void be32(uint8_t *p,uint32_t v){
 p[0]=(uint8_t)(v>>24);p[1]=(uint8_t)(v>>16);
 p[2]=(uint8_t)(v>>8);p[3]=(uint8_t)v;
}
static int guest_entry(ppu_context*c){
 const uint64_t lr=c->lr;
 c->gpr[3]=0x30000;c->gpr[4]=0x20050;c->lr=0x10400;
 int rc=ar_guest_call(c,0x10060);if(rc||c->gpr[3])return AR_BAD_ARGS;
 c->gpr[3]=0x30000;c->gpr[4]=0;c->lr=0x10404;
 rc=ar_guest_call(c,0x10080);if(rc||c->gpr[3])return AR_BAD_ARGS;
 if(ar_read32(0x30000)!=c->thread_id)return AR_BAD_ARGS;
 c->gpr[3]=0x30000;c->lr=0x10408;
 rc=ar_guest_call(c,0x10080);if(rc||c->gpr[3])return AR_BAD_ARGS;
 if(ar_read32(0x3000c)!=1u)return AR_BAD_ARGS;
 c->gpr[3]=0x30000;c->lr=0x1040c;
 rc=ar_guest_call(c,0x10090);if(rc||c->gpr[3])return AR_BAD_ARGS;
 if(ar_read32(0x3000c)!=0u || ar_read32(0x30000)!=c->thread_id)
   return AR_BAD_ARGS;
 c->gpr[3]=0x30000;c->lr=0x10410;
 rc=ar_guest_call(c,0x10090);if(rc||c->gpr[3])return AR_BAD_ARGS;
 if(ar_read32(0x30000)!=0xffffffffu)return AR_BAD_ARGS;
 c->gpr[3]=0x30100;c->lr=0x10414;
 rc=ar_guest_call(c,0x100a0);if(rc||c->gpr[3])return AR_BAD_ARGS;
 if(ar_read64(0x30100)!=c->thread_id)return AR_BAD_ARGS;
 c->lr=lr;c->gpr[3]=0;return AR_OK;
}
int main(void){
 uint8_t attr[16]={0};ppu_context ctx;ppu_context_init(&ctx);
 ctx.thread_id=7;ctx.lr=0x1ffff;
 if(ar_bridge_init(0x40000u)!=AR_OK)return 1;
 ar_lwmutex_reset();ar_lv2_bootstrap_reset();
 be32(attr,2u);be32(attr+4u,0x10u);memcpy(attr+8,"_lc_mtx",8);
 if(ar_vm_load(0x20050u,attr,sizeof(attr))!=AR_OK)return 2;
 if(ar_bind_import(0x10060u,0x2f85c0efu)!=AR_OK ||
    ar_bind_hle(0x2f85c0efu,ar_sys_lwmutex_create)!=AR_OK ||
    ar_bind_import(0x10080u,0x1573dc3fu)!=AR_OK ||
    ar_bind_hle(0x1573dc3fu,ar_sys_lwmutex_lock)!=AR_OK ||
    ar_bind_import(0x10090u,0x1bc200f4u)!=AR_OK ||
    ar_bind_hle(0x1bc200f4u,ar_sys_lwmutex_unlock)!=AR_OK ||
    ar_bind_import(0x100a0u,0x350d454eu)!=AR_OK ||
    ar_bind_hle(0x350d454eu,ar_lv2_thread_get_id)!=AR_OK ||
    ar_register(0x10000u,guest_entry)!=AR_OK)return 3;
 const int rc=ar_run(&ctx,0x10000u,64u);
 if(rc||ctx.gpr[3]||ar_lwmutex_created_count()!=1u ||
    ar_read32(0x30000u)!=0xffffffffu ||
    ar_read64(0x30100u)!=7u||ar_last_error()!=AR_OK){
    fprintf(stderr,"M79 native ABI rc=%d r3=%llu owner=%08x id=%llu\n",
       rc,(unsigned long long)ctx.gpr[3],ar_read32(0x30000u),
       (unsigned long long)ar_read64(0x30100u));return 4;
 }
 ar_bridge_shutdown();
 puts("M7.9 native AOT thread-ID, recursive lwmutex lock/unlock PASS");
 return 0;
}
