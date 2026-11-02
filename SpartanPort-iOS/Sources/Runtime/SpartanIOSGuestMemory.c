#include "SpartanIOSGuestMemory.h"

#include <errno.h>
#include <mach/mach.h>
#include <mach/vm_map.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>

/*
 * iOS deliberately does not expose the mach_vm_* API in its public SDK.
 * vm_* uses vm_address_t/vm_size_t, which are pointer-width on arm64 and
 * therefore cover the full 64-bit guest arena without private headers.
 */
struct SpartanGuestMemory {
    vm_address_t base;
    vm_size_t size;
};

static vm_size_t page_aligned_size(uint64_t size) {
    const uint64_t page = (uint64_t)vm_page_size;
    if (size == 0 || page == 0 || size > UINT64_MAX - (page - 1)) return 0;
    const uint64_t aligned = (size + page - 1) & ~(page - 1);
    if (aligned > (uint64_t)SIZE_MAX) return 0;
    return (vm_size_t)aligned;
}

static vm_prot_t mach_protection(int protection) {
    vm_prot_t result = VM_PROT_NONE;
    if (protection & PROT_READ) result |= VM_PROT_READ;
    if (protection & PROT_WRITE) result |= VM_PROT_WRITE;
    return result;
}

SpartanGuestMemory *spartan_guest_memory_create(uint64_t requested_size) {
    vm_size_t size = page_aligned_size(requested_size);
    if (!size) { errno = EINVAL; return NULL; }

    SpartanGuestMemory *memory = calloc(1, sizeof(*memory));
    if (!memory) return NULL;

    vm_address_t address = 0;
    kern_return_t kr = vm_allocate(mach_task_self(), &address, size, VM_FLAGS_ANYWHERE);
    if (kr != KERN_SUCCESS) {
        free(memory);
        errno = ENOMEM;
        return NULL;
    }

    kr = vm_protect(mach_task_self(), address, size, FALSE, VM_PROT_NONE);
    if (kr != KERN_SUCCESS) {
        vm_deallocate(mach_task_self(), address, size);
        free(memory);
        errno = ENOMEM;
        return NULL;
    }

    memory->base = address;
    memory->size = size;
    return memory;
}

void spartan_guest_memory_destroy(SpartanGuestMemory *memory) {
    if (!memory) return;
    (void)vm_deallocate(mach_task_self(), memory->base, memory->size);
    free(memory);
}

void *spartan_guest_memory_host_pointer(SpartanGuestMemory *memory, uint64_t guest_address,
                                        uint64_t length) {
    if (!memory || guest_address > (uint64_t)memory->size ||
        length > (uint64_t)memory->size - guest_address) {
        errno = EFAULT;
        return NULL;
    }
    return (void *)(uintptr_t)(memory->base + (vm_address_t)guest_address);
}

int spartan_guest_memory_protect(SpartanGuestMemory *memory, uint64_t guest_address,
                                 uint64_t length, int protection) {
    if (!memory || guest_address > (uint64_t)memory->size ||
        (protection & ~(PROT_READ | PROT_WRITE)) != 0) {
        errno = EINVAL;
        return -1;
    }
    if (!length) return 0;

    vm_size_t size = page_aligned_size(length);
    if (!size || guest_address % (uint64_t)vm_page_size != 0 ||
        size > (vm_size_t)((uint64_t)memory->size - guest_address)) {
        errno = EINVAL;
        return -1;
    }

    kern_return_t kr = vm_protect(mach_task_self(),
                                  memory->base + (vm_address_t)guest_address,
                                  size, FALSE, mach_protection(protection));
    if (kr != KERN_SUCCESS) { errno = EACCES; return -1; }
    return 0;
}

uint64_t spartan_guest_memory_size(const SpartanGuestMemory *memory) {
    return memory ? (uint64_t)memory->size : 0;
}
