#ifndef SPARTAN_IOS_G3PROBE_LOADER_H
#define SPARTAN_IOS_G3PROBE_LOADER_H
#include <stddef.h>
#include <stdint.h>
#include "SpartanIOSGuestMemory.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct SpartanG3ProbeImage SpartanG3ProbeImage;
typedef struct {
    uint64_t image_size, entry_offset, import_count, binding_count;
    uint64_t module_count, segment_count, relocation_count;
    uint64_t unresolved_import_count, applied_relocation_count;
    uint64_t image_base;
} SpartanG3ProbeInfo;
/* Load the exact G3PROBE5 image emitted by gow3-macos-arm64/scripts/link_modules.py.
 * Relocations are applied to data-only host memory. Unresolved imports are counted and
 * remain zero; callers MUST NOT start the game while that count is nonzero.
 * TLS relocations use the supplied GS displacement (normally zero for bbcpu's TCB base).
 * No guest page is made executable. */
SpartanG3ProbeImage *spartan_g3probe_load(const void *bytes, size_t length,
                                         uint32_t gs_displacement,
                                         char *error, size_t error_capacity);
void spartan_g3probe_destroy(SpartanG3ProbeImage *image);
SpartanGuestMemory *spartan_g3probe_memory(SpartanG3ProbeImage *image);
uint64_t spartan_g3probe_entry(const SpartanG3ProbeImage *image);
int spartan_g3probe_info(const SpartanG3ProbeImage *image, SpartanG3ProbeInfo *info);
#ifdef __cplusplus
}
#endif
#endif
