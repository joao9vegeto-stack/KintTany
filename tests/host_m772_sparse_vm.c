#include "ppu_bridge.h"
#include <stdint.h>
#include <stdio.h>

/* The bridge normally resolves these through the PS3Recomp archive. This
 * host regression test exercises only the virtual address reservation. */
int ar_m772_dispatch_native(ppu_context *ctx,uint32_t pc)
{ (void)ctx; (void)pc; return 0; }
void ar_m772_unbind_guest_memory(void *guest_memory) { (void)guest_memory; }

static int check_word(uint32_t guest_address,uint32_t expected)
{
  ar_write32(guest_address,expected);
  return ar_read32(guest_address)==expected;
}

int main(void)
{
  const size_t guest_size=(size_t)UINT32_C(0xE0000000);
  if(ar_bridge_init((size_t)256u*1024u*1024u)!=AR_OK){
    puts("[FAIL] sparse VM reserve/commit");return 1;
  }
  uint8_t *base=(uint8_t*)ar_guest_memory_base();
  if(!base || ((uintptr_t)base&UINT64_C(0xFFFFFFFF))!=0 ||
     ar_guest_memory_capacity()!=guest_size){
    puts("[FAIL] 4-GiB alignment or 3.5-GiB guest window");
    ar_bridge_shutdown();return 1;
  }
  if(!check_word(UINT32_C(0x11019000),UINT32_C(0x1234ABCD)) ||
     !check_word(UINT32_C(0xC0000000),UINT32_C(0x52535821)) ||
     !check_word(UINT32_C(0xD0000000),UINT32_C(0x5354414B))){
    puts("[FAIL] low/mmapper, RSX-local, or thread-stack memory");
    ar_bridge_shutdown();return 1;
  }
  uint8_t byte=0;
  if(ar_vm_read_bytes(UINT32_C(0xE0000000),&byte,1)!=AR_MEM_FAULT){
    puts("[FAIL] out-of-window guest address accepted");
    ar_bridge_shutdown();return 1;
  }
  ar_bridge_shutdown();
  puts("[PASS] sparse M772 guest VM: 4-GiB aligned; mmapper, RSX and stack ranges readable/writable; upper bound guarded");
  return 0;
}
