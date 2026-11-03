#ifndef SPARTAN_IOS_AOT_RUNTIME_H
#define SPARTAN_IOS_AOT_RUNTIME_H
#include <stddef.h>
#include <stdint.h>
int SpartanIOSAOTRegister(uintptr_t image_base, size_t executable_size, const char *library_path);
uint64_t SpartanIOSAOTCall(uintptr_t entry, const uint64_t *arguments, int argument_count, void *guest_stack, size_t guest_stack_size);
void SpartanIOSAOTSetThreadPointer(uintptr_t guest_tcb);
int SpartanIOSAOTIsRegistered(void);
int SpartanIOSAOTFunctionCount(void);
#endif
