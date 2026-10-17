#include "ppu_mmapper.h"
#include <stdint.h>
#include <stdio.h>
static int native_entry(ppu_context*c){
 c->gpr[3]=0x20000000u;c->gpr[4]=0x400u;
 c->gpr[5]=0;c->gpr[6]=0x20000;c->gpr[11]=0x14au;
 int rc=ar_guest_syscall(c);
 if(rc||c->gpr[3]||ar_read32(0x20000)!=0x20000000u)return AR_BAD_ARGS;
 return AR_OK;
}
int main(void){
 ppu_context c;ppu_context_init(&c);c.thread_id=1;
 if(ar_bridge_init(0x40000)!=AR_OK)return 1;
 ar_mmapper_reset();
 if(ar_bind_syscall(0x14au,ar_sys_mmapper_allocate_address)!=AR_OK||
    ar_register(0x10000u,native_entry)!=AR_OK)return 2;
 if(ar_run(&c,0x10000u,64u)!=AR_OK||ar_mmapper_reservation_count()!=1u)return 3;
 c.gpr[3]=0x100000;c.gpr[4]=0x400;c.gpr[5]=0x20004;
 if(ar_sys_mmapper_allocate_memory(&c)!=AR_OK||c.gpr[3]!=0||
    ar_read32(0x20004)!=0x08000000u)return 4;
 c.gpr[3]=0x20000000;c.gpr[4]=0x08000000;c.gpr[5]=0x40000;
 if(ar_sys_mmapper_map_memory(&c)!=AR_OK||c.gpr[3]||ar_mmapper_mapped_count()!=1)return 5;
 ar_write32(0x20000000u,0x1234abcdu);
 if(ar_last_error()!=AR_OK||ar_read32(0x20000000u)!=0x1234abcdu)return 6;
 c.gpr[3]=0x20000000;c.gpr[4]=0x20008;
 if(ar_sys_mmapper_unmap_memory(&c)!=AR_OK||c.gpr[3]||
    ar_mmapper_mapped_count()||ar_read32(0x20008)!=0x08000000u)return 7;
 c.gpr[3]=0x08000000;
 if(ar_sys_mmapper_free_memory(&c)!=AR_OK||c.gpr[3]||ar_mmapper_object_count())return 8;
 ar_mmapper_reset();ar_bridge_shutdown();
 puts("M7.11 native PPU virtual reservation, physical map and unmap PASS");
 return 0;
}
