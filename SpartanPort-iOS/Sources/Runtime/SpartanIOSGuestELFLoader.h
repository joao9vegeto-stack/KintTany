#ifndef SPARTAN_IOS_GUEST_ELF_LOADER_H
#define SPARTAN_IOS_GUEST_ELF_LOADER_H
#include <stddef.h>
#include <stdint.h>
#include "SpartanIOSGuestMemory.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct SpartanGuestELF SpartanGuestELF;
typedef struct { uint64_t virtual_address, memory_size, file_size; uint32_t flags; } SpartanGuestELFSegment;
/* Stage a reconstructed ELF64 little-endian x86-64 image in data-only guest memory.
 * No SELF decryption, relocation, PRX loading, import resolution or execution. */
SpartanGuestELF *spartan_guest_elf_load(const void *bytes, size_t length, char *error, size_t error_capacity);
void spartan_guest_elf_destroy(SpartanGuestELF *image);
SpartanGuestMemory *spartan_guest_elf_memory(SpartanGuestELF *image);
uint64_t spartan_guest_elf_entry(const SpartanGuestELF *image);
size_t spartan_guest_elf_segment_count(const SpartanGuestELF *image);
int spartan_guest_elf_segment(const SpartanGuestELF *image, size_t index, SpartanGuestELFSegment *out_segment);
#ifdef __cplusplus
}
#endif
#endif
