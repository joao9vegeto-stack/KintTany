#ifndef SPARTANPORT_BRIDGING_HEADER_H
#define SPARTANPORT_BRIDGING_HEADER_H
#include "Runtime/SpartanIOSGuestMemory.h"
#include "Runtime/ThirdParty/bbcpu.h"
#include <stddef.h>
#include <stdint.h>

/* Register the generated game functions against the staged guest image.
 * The caller must first map every PT_LOAD segment and provide its executable range. */
int SpartanIOSAOTRegister(uintptr_t image_base, size_t executable_size, const char *recompiled_library_path);
uint64_t SpartanIOSAOTCall(uintptr_t entry, const uint64_t *arguments, int argument_count, void *guest_stack, size_t guest_stack_size);
void SpartanIOSAOTSetThreadPointer(uintptr_t guest_tcb);
int SpartanKosmicKrispProbe(void);
const char *SpartanKosmicKrispProbeMessage(void);
#endif
int SpartanIOSAOTIsRegistered(void);
int SpartanIOSAOTFunctionCount(void);
