/* Strict read-only PPU ELF64 image staging (not SELF decryption). */
#ifndef AR_ELF_IMAGE_H
#define AR_ELF_IMAGE_H
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
 uint32_t entry_code,entry_descriptor,toc,segments;
 uint64_t loaded_bytes,bss_bytes;
} ar_elf_image_result;
/* Call ar_bridge_init(guest_capacity) first. Verify before mapping. */
int ar_load_elf_image(const uint8_t*,size_t,size_t,ppu_context*,ar_elf_image_result*);
#ifdef __cplusplus
}
#endif
#endif
