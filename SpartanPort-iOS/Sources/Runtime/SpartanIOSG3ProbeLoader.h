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
 uint64_t image_size,entry_offset,procparam_offset,flags,import_count,binding_count,module_count,segment_count,relocation_count;
 uint64_t unresolved_import_count,applied_relocation_count,image_base;
 uint64_t main_tls_address,main_tls_file_size,main_tls_memory_size,main_tls_alignment;
} SpartanG3ProbeInfo;
typedef struct { uint64_t base,size,init,tls_address,tls_memory_size,tls_file_size,tls_module_id; } SpartanG3ProbeModule;
typedef struct { uint64_t offset,size,flags; } SpartanG3ProbeSegment;
SpartanG3ProbeImage *spartan_g3probe_load(const void *bytes,size_t length,char *error,size_t error_capacity);
void spartan_g3probe_destroy(SpartanG3ProbeImage *image);
SpartanGuestMemory *spartan_g3probe_memory(SpartanG3ProbeImage *image);
uint64_t spartan_g3probe_entry(const SpartanG3ProbeImage *image);
int spartan_g3probe_info(const SpartanG3ProbeImage *image,SpartanG3ProbeInfo *info);
int spartan_g3probe_module(const SpartanG3ProbeImage *image,uint64_t index,SpartanG3ProbeModule *module);
int spartan_g3probe_segment(const SpartanG3ProbeImage *image,uint64_t index,SpartanG3ProbeSegment *segment);
#ifdef __cplusplus
}
#endif
#endif
