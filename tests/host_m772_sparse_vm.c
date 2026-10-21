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
  ar_vm_reservation_status reservation={0};
  ar_bridge_vm_reservation_status(&reservation);
  if(!reservation.attempted || !reservation.reservation_kind ||
     reservation.failure_stage!=AR_VM_STAGE_NONE ||
     reservation.failure_errno!=0 ||
     (reservation.reservation_kind==1u && !reservation.hint_attempts)){
    puts("[FAIL] sparse VM reservation strategy diagnostics");
    ar_bridge_shutdown();return 1;
  }
  if(reservation.reservation_kind==3u && !reservation.mach_attempts){
    puts("[FAIL] Mach fixed reservation did not record attempts");
    ar_bridge_shutdown();return 1;
  }
#if defined(__APPLE__)
  if(reservation.reservation_kind!=3u){
    puts("[FAIL] Apple host did not reserve guest VM through the Mach fixed path");
    ar_bridge_shutdown();return 1;
  }
#endif
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
  const char *strategy=reservation.reservation_kind==3u?"mach-fixed":
      reservation.reservation_kind==1u?"aligned-hint":"overmap-fallback";
  printf("[PASS] sparse M772 guest VM: 4-GiB aligned; strategy=%s; Mach attempts=%u; mmap hint attempts=%u; mmapper, RSX and stack ranges readable/writable; upper bound guarded\n",
      strategy,reservation.mach_attempts,reservation.hint_attempts);
  return 0;
}
