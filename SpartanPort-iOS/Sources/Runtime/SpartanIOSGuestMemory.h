#ifndef SPARTAN_IOS_GUEST_MEMORY_H
#define SPARTAN_IOS_GUEST_MEMORY_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SpartanGuestMemory SpartanGuestMemory;

/* Data-only guest address arena. Guest virtual addresses are offsets from
 * the host base. This API never creates executable memory or generates code. */
SpartanGuestMemory *spartan_guest_memory_create(uint64_t size);
void spartan_guest_memory_destroy(SpartanGuestMemory *memory);
void *spartan_guest_memory_host_pointer(SpartanGuestMemory *memory, uint64_t guest_address,
                                        uint64_t length);
/* Only PROT_READ and PROT_WRITE are accepted. PROT_EXEC is deliberately rejected:
 * ARM64 AOT code must be compiled and linked into the signed app at build time. */
int spartan_guest_memory_protect(SpartanGuestMemory *memory, uint64_t guest_address,
                                 uint64_t length, int protection);
uint64_t spartan_guest_memory_size(const SpartanGuestMemory *memory);

#ifdef __cplusplus
}
#endif
#endif
