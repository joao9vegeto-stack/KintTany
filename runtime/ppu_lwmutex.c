/* M7.7 authentic sys_lwmutex_create (sysPrxForUser NID 0x2F85C0EF).
 * Reference ABI: sys_lwmutex_attribute_t: BE u32 protocol, BE u32
 * recursive, 8-byte name. sys_lwmutex_t: BE u32 owner, waiter,
 * attribute, recursive_count, sleep_queue, pad (24 bytes).
 * This supports creation and state tracking for bounded single-threaded
 * bootstrap ONLY. Lock/unlock/recursive waits are NOT implemented here. */
#include "ppu_lwmutex.h"
#include <stdint.h>
#include <stddef.h>
enum { AR_LW_MAX=128, AR_LW_FREE=0xffffffffu,
       AR_LW_SYS_ID_FIRST=0x95000000u, AR_LW_EINVAL=0x80010002u,
       AR_LW_EBUSY=0x8001000Au, AR_LW_ENOMEM=0x80010004u,
       AR_LW_PROTO_FIFO=1, AR_LW_PROTO_PRIORITY=2, AR_LW_PROTO_RETRY=4,
       AR_LW_RECURSIVE=0x10, AR_LW_NONRECURSIVE=0x20 };
static struct {uint32_t guest_address, handle;} entries[AR_LW_MAX];
static unsigned created;
void ar_lwmutex_reset(void){created=0u;}
unsigned ar_lwmutex_created_count(void){return created;}
int ar_sys_lwmutex_create(ppu_context *cpu){
 if(!cpu)return AR_BAD_ARGS;
 uint64_t guest_addr=cpu->gpr[3], attr_addr=cpu->gpr[4];
 if(!guest_addr||!attr_addr||(guest_addr&7u)||(attr_addr&7u)||
    guest_addr>UINT32_MAX-23u||attr_addr>UINT32_MAX-15u){
   cpu->gpr[3]=AR_LW_EINVAL;return AR_OK;
 }
 /* Probe both complete guest ranges before any output writes.
  * Invalid guest memory faults MUST propagate, never return success. */
 (void)ar_read8(guest_addr+23u);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 (void)ar_read8(attr_addr+15u);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 uint32_t protocol=ar_read32(attr_addr),recursive=ar_read32(attr_addr+4u);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 if((protocol!=AR_LW_PROTO_FIFO && protocol!=AR_LW_PROTO_PRIORITY &&
     protocol!=AR_LW_PROTO_RETRY) ||
    (recursive!=AR_LW_RECURSIVE && recursive!=AR_LW_NONRECURSIVE)){
   cpu->gpr[3]=AR_LW_EINVAL;return AR_OK;
 }
 for(unsigned i=0;i<created;i++)
  if(entries[i].guest_address==(uint32_t)guest_addr){
    cpu->gpr[3]=AR_LW_EBUSY;return AR_OK;
  }
 if(created==AR_LW_MAX){
   cpu->gpr[3]=AR_LW_ENOMEM;return AR_OK;
 }
 const uint32_t id=AR_LW_SYS_ID_FIRST+created;
 ar_write32(guest_addr,AR_LW_FREE); /* owner */
 ar_write32(guest_addr+4u,0u); /* waiter */
 ar_write32(guest_addr+8u,protocol|recursive);
 ar_write32(guest_addr+12u,0u); /* recursive_count */
 ar_write32(guest_addr+16u,id); /* sleep_queue / kernel pseudo-id */
 ar_write32(guest_addr+20u,0u); /* pad */
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 entries[created].guest_address=(uint32_t)guest_addr;
 entries[created].handle=id;
 created++;
 cpu->gpr[3]=0u; /* CELL_OK only after complete memory initialization */
 return AR_OK;
}
