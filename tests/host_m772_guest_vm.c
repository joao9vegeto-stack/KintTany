#include "ppu_mmapper.h"
#include <stdint.h>
#include <stdio.h>

/* The bridge normally resolves these through the PS3Recomp archive. This
 * host regression test exercises the guest VM reservation and bounds. */
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
    puts("[FAIL] guest VM reservation");return 1;
  }
  uint8_t *base=(uint8_t*)ar_guest_memory_base();
  if(!base || ar_guest_memory_capacity()!=guest_size){
    puts("[FAIL] exact 3.5-GiB guest window");
    ar_bridge_shutdown();return 1;
  }
  ar_vm_reservation_status reservation={0};
  ar_bridge_vm_reservation_status(&reservation);
  if(!reservation.attempted || !reservation.reservation_kind ||
     reservation.failure_stage!=AR_VM_STAGE_NONE ||
     reservation.failure_errno!=0 ||
     (reservation.reservation_kind==1u && !reservation.mmap_attempts) ||
     reservation.reservation_base!=(uint64_t)(uintptr_t)base){
    puts("[FAIL] guest VM reservation strategy diagnostics");
    ar_bridge_shutdown();return 1;
  }
  if(reservation.reservation_kind==3u && !reservation.mach_attempts){
    puts("[FAIL] Mach anywhere reservation did not record attempts");
    ar_bridge_shutdown();return 1;
  }
  if(!check_word(UINT32_C(0x11019000),UINT32_C(0x1234ABCD)) ||
     !check_word(UINT32_C(0xC0000000),UINT32_C(0x52535821)) ||
     !check_word(UINT32_C(0xD0000000),UINT32_C(0x5354414B))){
    puts("[FAIL] guest RAM, RSX-local, or thread-stack memory");
    ar_bridge_shutdown();return 1;
  }
  ar_write8(UINT32_C(0x045C0573),UINT8_C(0xA5));
  if(ar_read8(UINT32_C(0x045C0573))!=UINT8_C(0xA5)){
    puts("[FAIL] guest VM probe offset 0x045C0573 is not readable/writable");
    ar_bridge_shutdown();return 1;
  }
  /* Exercise the M772 production configuration: mmapper EAs are inside the
   * full guest window, so map/unmap must stage bytes into the native VM and
   * preserve guest writes in the allocated object across a remap. */
  ppu_context mapper;
  ppu_context_init(&mapper);
  ar_mmapper_reset();
  mapper.gpr[3]=UINT32_C(0x10000000);
  mapper.gpr[4]=UINT32_C(0x400);
  mapper.gpr[5]=0;
  mapper.gpr[6]=UINT32_C(0x20000);
  if(ar_sys_mmapper_allocate_address(&mapper)!=AR_OK || mapper.gpr[3] ||
     ar_mmapper_reservation_count()!=1u){
    puts("[FAIL] mmapper guest address reservation");
    ar_bridge_shutdown();return 1;
  }
  const uint32_t guest_addr=ar_read32(UINT32_C(0x20000));
  mapper.gpr[3]=UINT32_C(0x100000);
  mapper.gpr[4]=UINT32_C(0x400);
  mapper.gpr[5]=UINT32_C(0x20004);
  if(ar_sys_mmapper_allocate_memory(&mapper)!=AR_OK || mapper.gpr[3]){
    puts("[FAIL] mmapper backing allocation");
    ar_bridge_shutdown();return 1;
  }
  const uint32_t memory_id=ar_read32(UINT32_C(0x20004));
  mapper.gpr[3]=guest_addr;mapper.gpr[4]=memory_id;mapper.gpr[5]=0;
  if(ar_sys_mmapper_map_memory(&mapper)!=AR_OK || mapper.gpr[3]){
    puts("[FAIL] mmapper map into full guest VM");
    ar_bridge_shutdown();return 1;
  }
  ar_write32(guest_addr,UINT32_C(0x1234ABCD));
  mapper.gpr[3]=guest_addr;mapper.gpr[4]=UINT32_C(0x20008);
  if(ar_sys_mmapper_unmap_memory(&mapper)!=AR_OK || mapper.gpr[3] ||
     ar_read32(UINT32_C(0x20008))!=memory_id){
    puts("[FAIL] mmapper unmap and copyback");
    ar_bridge_shutdown();return 1;
  }
  mapper.gpr[3]=guest_addr;mapper.gpr[4]=memory_id;mapper.gpr[5]=0;
  if(ar_sys_mmapper_map_memory(&mapper)!=AR_OK || mapper.gpr[3] ||
     ar_read32(guest_addr)!=UINT32_C(0x1234ABCD)){
    puts("[FAIL] mmapper remap did not preserve guest writes");
    ar_bridge_shutdown();return 1;
  }
  mapper.gpr[3]=guest_addr;mapper.gpr[4]=UINT32_C(0x20008);
  if(ar_sys_mmapper_unmap_memory(&mapper)!=AR_OK || mapper.gpr[3]){
    puts("[FAIL] mmapper final unmap");
    ar_bridge_shutdown();return 1;
  }
  mapper.gpr[3]=memory_id;
  if(ar_sys_mmapper_free_memory(&mapper)!=AR_OK || mapper.gpr[3]){
    puts("[FAIL] mmapper free after unmap");
    ar_bridge_shutdown();return 1;
  }
  ar_mmapper_reset();
  uint8_t byte=0;
  if(ar_vm_read_bytes(UINT32_C(0xE0000000),&byte,1)!=AR_MEM_FAULT){
    puts("[FAIL] out-of-window guest address accepted by checked bridge");
    ar_bridge_shutdown();return 1;
  }
  ar_bridge_shutdown();
  const char *strategy=reservation.reservation_kind==3u?"mach-anywhere":
      reservation.reservation_kind==1u?"mmap-anywhere":"unknown";
  printf("[PASS] M772 guest VM: exact 3.5-GiB extent anywhere; strategy=%s; base=0x%llX; Mach attempts=%u; mmap attempts=%u; RAM EA 0x045C0573, RSX, stack, mmapper map/unmap/remap and copyback PASS; bridge upper bound enforced\n",
      strategy,(unsigned long long)reservation.reservation_base,
      reservation.mach_attempts,reservation.mmap_attempts);
  return 0;
}
