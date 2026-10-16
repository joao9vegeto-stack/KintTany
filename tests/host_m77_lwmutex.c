/* M7.7 PS3 sysPrxForUser lwmutex create ABI regression. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_lwmutex.h"
enum { CELL_EINVAL=0x80010002u, CELL_EBUSY=0x8001000au };
static void be32(uint8_t *p,uint32_t v){
 p[0]=(uint8_t)(v>>24);p[1]=(uint8_t)(v>>16);
 p[2]=(uint8_t)(v>>8);p[3]=(uint8_t)v;
}
static int call(ppu_context *c,uint32_t dst,uint32_t attr) {
 c->gpr[3]=dst;c->gpr[4]=attr;
 return ar_run(c,0x10060u,10u);
}
int main(void){
 uint8_t attr[16]={0}; ppu_context ctx;
 ppu_context_init(&ctx);
 if(ar_bridge_init(0x40000)!=AR_OK)return 1;
 ar_lwmutex_reset();
 if(ar_bind_import(0x10060u,0x2f85c0efu)!=AR_OK ||
    ar_bind_hle(0x2f85c0efu,ar_sys_lwmutex_create)!=AR_OK)return 2;
 be32(attr,2u);be32(attr+4u,0x10u);
 memcpy(attr+8,"_lc_mtx",8);
 if(ar_vm_load(0x20050u,attr,sizeof(attr))!=AR_OK)return 3;
 ctx.gpr[2]=0x12345678u;ctx.lr=0x10410u;
 if(call(&ctx,0x30000u,0x20050u)!=AR_OK ||
    ctx.gpr[3]!=0u || ar_lwmutex_created_count()!=1u ||
    ar_read32(0x30000u)!=0xffffffffu ||
    ar_read32(0x30004u)!=0u ||
    ar_read32(0x30008u)!=0x12u ||
    ar_read32(0x3000cu)!=0u ||
    ar_read32(0x30010u)!=0x95000000u ||
    ar_read32(0x30014u)!=0u ||
    ctx.gpr[2]!=0x12345678u || ctx.cia!=0x10410u) return 4;
 if(call(&ctx,0x30000u,0x20050u)!=AR_OK ||
    ctx.gpr[3]!=CELL_EBUSY || ar_lwmutex_created_count()!=1u)return 5;
 be32(attr+4u,0xDEu);
 if(ar_vm_load(0x20050u,attr,sizeof(attr))!=AR_OK)return 6;
 if(call(&ctx,0x30020u,0x20050u)!=AR_OK ||
    ctx.gpr[3]!=CELL_EINVAL || ar_lwmutex_created_count()!=1u ||
    ar_read32(0x30020u)!=0u)return 7;
 be32(attr+4u,0x20u);
 if(ar_vm_load(0x20050u,attr,sizeof(attr))!=AR_OK)return 8;
 if(call(&ctx,0x30020u,0x20050u)!=AR_OK ||
    ctx.gpr[3]!=0u || ar_lwmutex_created_count()!=2u ||
    ar_read32(0x30028u)!=0x22u ||
    ar_read32(0x30030u)!=0x95000001u)return 9;
 if(call(&ctx,0x30022u,0x20050u)!=AR_OK ||
    ctx.gpr[3]!=CELL_EINVAL || ar_lwmutex_created_count()!=2u)return 10;
 ar_bridge_shutdown();
 if(ar_bridge_init(0x40000u)!=AR_OK)return 11;
 ar_lwmutex_reset();
 if(ar_lwmutex_created_count()!=0u)return 12;
 ar_bridge_shutdown();
 puts("M7.7 lwmutex create guest BE ABI, validation, reset PASS");
 return 0;
}
