#include "SpartanIOSGuestMemory.h"

#include <errno.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <libkern/OSCacheControl.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

struct SpartanGuestMemory {
    mach_vm_address_t base;
    mach_vm_size_t size;
};

struct SpartanJITRegion {
    void *address;
    size_t size;
    bool writing;
};

static mach_vm_size_t page_aligned_size(uint64_t size) {
    const uint64_t page = (uint64_t)vm_page_size;
    if (size == 0 || size > UINT64_MAX - (page - 1)) return 0;
    return (mach_vm_size_t)((size + page - 1) & ~(page - 1));
}

static vm_prot_t mach_protection(int protection) {
    vm_prot_t result = VM_PROT_NONE;
    if (protection & PROT_READ) result |= VM_PROT_READ;
    if (protection & PROT_WRITE) result |= VM_PROT_WRITE;
    if (protection & PROT_EXEC) result |= VM_PROT_EXECUTE;
    return result;
}

SpartanGuestMemory *spartan_guest_memory_create(uint64_t requested_size) {
    mach_vm_size_t size = page_aligned_size(requested_size);
    if (!size) { errno = EINVAL; return NULL; }
    SpartanGuestMemory *memory = calloc(1, sizeof(*memory));
    if (!memory) return NULL;

    mach_vm_address_t address = 0;
    kern_return_t kr = mach_vm_allocate(mach_task_self(), &address, size, VM_FLAGS_ANYWHERE);
    if (kr != KERN_SUCCESS) {
        free(memory);
        errno = ENOMEM;
        return NULL;
    }
    /* Reserve the full range inaccessible. Guest mappings explicitly opt in
       to access; this prevents accidental reads of uncommitted guest pages. */
    kr = mach_vm_protect(mach_task_self(), address, size, FALSE, VM_PROT_NONE);
    if (kr != KERN_SUCCESS) {
        mach_vm_deallocate(mach_task_self(), address, size);
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
    mach_vm_deallocate(mach_task_self(), memory->base, memory->size);
    free(memory);
}

void *spartan_guest_memory_host_pointer(SpartanGuestMemory *memory, uint64_t guest_address,
                                        uint64_t length) {
    if (!memory || guest_address > memory->size || length > memory->size - guest_address) {
        errno = EFAULT;
        return NULL;
    }
    return (void *)(uintptr_t)(memory->base + guest_address);
}

int spartan_guest_memory_protect(SpartanGuestMemory *memory, uint64_t guest_address,
                                 uint64_t length, int protection) {
    if (!memory || guest_address > memory->size || length > memory->size - guest_address ||
        (protection & ~(PROT_READ | PROT_WRITE | PROT_EXEC))) {
        errno = EINVAL;
        return -1;
    }
    if (!length) return 0;
    mach_vm_address_t address = memory->base + guest_address;
    mach_vm_size_t size = page_aligned_size(length);
    if (!size || guest_address % vm_page_size) { errno = EINVAL; return -1; }
    kern_return_t kr = mach_vm_protect(mach_task_self(), address, size, FALSE,
                                       mach_protection(protection));
    if (kr != KERN_SUCCESS) { errno = EACCES; return -1; }
    return 0;
}

uint64_t spartan_guest_memory_size(const SpartanGuestMemory *memory) {
    return memory ? memory->size : 0;
}

SpartanJITRegion *spartan_jit_region_create(size_t requested_size) {
#ifndef MAP_JIT
    (void)requested_size;
    errno = ENOTSUP;
    return NULL;
#else
    long page = sysconf(_SC_PAGESIZE);
    if (page <= 0 || requested_size == 0 || requested_size > SIZE_MAX - (size_t)page) {
        errno = EINVAL;
        return NULL;
    }
    size_t size = (requested_size + (size_t)page - 1) & ~((size_t)page - 1);
    void *address = mmap(NULL, size, PROT_READ | PROT_WRITE | PROT_EXEC,
                         MAP_PRIVATE | MAP_ANON | MAP_JIT, -1, 0);
    if (address == MAP_FAILED) return NULL;
    SpartanJITRegion *region = calloc(1, sizeof(*region));
    if (!region) { munmap(address, size); return NULL; }
    region->address = address;
    region->size = size;
    /* Default to executable/read-only mode. */
    pthread_jit_write_protect_np(1);
    return region;
#endif
}

void spartan_jit_region_destroy(SpartanJITRegion *region) {
    if (!region) return;
    if (region->writing) pthread_jit_write_protect_np(1);
    munmap(region->address, region->size);
    free(region);
}

void *spartan_jit_region_address(SpartanJITRegion *region) {
    return region ? region->address : NULL;
}

int spartan_jit_region_begin_write(SpartanJITRegion *region) {
    if (!region || region->writing) { errno = EINVAL; return -1; }
    pthread_jit_write_protect_np(0);
    region->writing = true;
    return 0;
}

int spartan_jit_region_end_write(SpartanJITRegion *region) {
    if (!region || !region->writing) { errno = EINVAL; return -1; }
    __builtin___clear_cache((char *)region->address, (char *)region->address + region->size);
    pthread_jit_write_protect_np(1);
    region->writing = false;
    return 0;
}

void spartan_jit_region_invalidate(SpartanJITRegion *region, size_t offset, size_t length) {
    if (!region || offset > region->size || length > region->size - offset) return;
    char *start = (char *)region->address + offset;
    sys_icache_invalidate(start, length);
}
