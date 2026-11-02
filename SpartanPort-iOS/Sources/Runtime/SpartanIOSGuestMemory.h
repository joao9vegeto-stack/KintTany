#ifndef SPARTAN_IOS_GUEST_MEMORY_H
#define SPARTAN_IOS_GUEST_MEMORY_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SpartanGuestMemory SpartanGuestMemory;
typedef struct SpartanJITRegion SpartanJITRegion;

/* Reserve one contiguous, relocatable guest address space. Guest virtual
 * addresses are offsets from the returned arena base; no forbidden fixed
 * low-address mapping is attempted on iOS. */
SpartanGuestMemory *spartan_guest_memory_create(uint64_t size);
void spartan_guest_memory_destroy(SpartanGuestMemory *memory);
void *spartan_guest_memory_host_pointer(SpartanGuestMemory *memory, uint64_t guest_address,
                                        uint64_t length);
int spartan_guest_memory_protect(SpartanGuestMemory *memory, uint64_t guest_address,
                                 uint64_t length, int protection);
uint64_t spartan_guest_memory_size(const SpartanGuestMemory *memory);

/* W^X JIT region. Code may only be modified inside begin_write/end_write;
 * executable access is restored before guest code is entered. */
SpartanJITRegion *spartan_jit_region_create(size_t size);
void spartan_jit_region_destroy(SpartanJITRegion *region);
void *spartan_jit_region_address(SpartanJITRegion *region);
int spartan_jit_region_begin_write(SpartanJITRegion *region);
int spartan_jit_region_end_write(SpartanJITRegion *region);
void spartan_jit_region_invalidate(SpartanJITRegion *region, size_t offset, size_t length);

#ifdef __cplusplus
}
#endif
#endif
