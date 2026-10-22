#!/usr/bin/env python3
"""PoPTST Build 15 iPhoneOS VM: lazy 4-GiB guest reservation, sandbox
file-backed RAM mirrors, exact mapping ownership, and failure provenance.
Apply AFTER patch_repop_ios.py to pinned rePOP. Fail if upstream changes.
"""
from pathlib import Path
import sys

def one(s, old, new, label):
    n=s.count(old)
    if n != 1: raise RuntimeError(f'{label}: expected 1 anchor, got {n}: {old[:95]!r}')
    return s.replace(old,new,1)

def main(root):
    compat=root/'port/third_party/xboxrecomp/src/platform/win32_compat.c'
    s=compat.read_text()
    # iPhone app sandbox does not guarantee a globally named POSIX SHM
    # namespace. An unlinked sparse file in the app-private TMPDIR is a
    # genuine shared mmap backing, preserving RAM aliases without guest data
    # in the IPA or outside sandbox. Linux/macOS SHM behavior remains intact.
    s=one(s,'''    static volatile LONG map_counter = 0;
    char shm_name[32];
    LONG seq = InterlockedIncrement(&map_counter);
    const char *base = name ? name : "xbox_map";
    snprintf(shm_name, sizeof(shm_name), "/%s_%ld", base, seq);
    int fd = shm_open(shm_name, O_CREAT | O_RDWR | O_EXCL, 0600);
    if (fd >= 0) shm_unlink(shm_name);
    return fd;''', '''#if TARGET_OS_IPHONE
    /* File is private to this app and removed from the directory
       immediately: mmap stays valid for the lifetime of the fd. */
    (void)name;
    char temp_path[1024];
    const char *tmp = getenv("TMPDIR");
    if (!tmp || !*tmp) tmp = "/tmp";
    int n = snprintf(temp_path, sizeof(temp_path), "%s%sPoPTST-RAM-XXXXXX",
                     tmp, tmp[strlen(tmp)-1] == '/' ? "" : "/");
    if (n < 0 || (size_t)n >= sizeof(temp_path)) { errno = ENAMETOOLONG; return -1; }
    int fd = mkstemp(temp_path);
    if (fd >= 0) unlink(temp_path);
    if (fd < 0) fprintf(stderr, "PoPTST VM B15: private RAM fd unavailable (errno=%d)\\n", errno);
    return fd;
#else
    static volatile LONG map_counter = 0;
    char shm_name[32];
    LONG seq = InterlockedIncrement(&map_counter);
    const char *base = name ? name : "xbox_map";
    snprintf(shm_name, sizeof(shm_name), "/%s_%ld", base, seq);
    int fd = shm_open(shm_name, O_CREAT | O_RDWR | O_EXCL, 0600);
    if (fd >= 0) shm_unlink(shm_name);
    return fd;
#endif''','iOS file-backed RAM vs global SHM')
    # In upstream VirtualAlloc, PAGE_NOACCESS maps to prot=0 but the portable
    # fallback mistakenly converts that to PROT_READ|PROT_WRITE. Reserving the
    # complete Xbox address space then counts as 4 GiB committed memory.
    # Reserve it as PROT_NONE and replace ONLY pages inside our owned range.
    s=one(s,'#if defined(__ANDROID__)\n    /* RE-SoT: a pure reservation commits nothing.',
          '#if defined(__ANDROID__) || (defined(__APPLE__) && TARGET_OS_IPHONE)\n    /* RE-SoT: a pure reservation commits nothing.',
          '4GiB iOS virtual reservation is PROT_NONE')
    s=one(s,'''        p = mmap(address, size, PROT_NONE, flags, -1, 0);
    } else''','''        p = mmap(address, size, PROT_NONE, flags, -1, 0);
        if (p == MAP_FAILED) {
            fprintf(stderr, "PoPTST VM B15: 4GiB reservation failed size=%zu errno=%d\\n",size,errno);
        }
    } else''','diagnostic reservation')
    # B21: iOS SIGBUS at guest 0x809B6000 was __bzero in
    # xbox_ContiguousAlloc, in a mapped file VMA that was r-- instead of rw-.
    # Real iOS host pages are 16KiB; Xbox alloc pages are 4KiB.
    # Portable mprotect(guest_4K_address,size) fails when unaligned.
    # Never discard or fake permissions; apply them to host-page coverage.
    s=one(s,'''BOOL VirtualProtect(LPVOID address, SIZE_T size, DWORD newProtect, PDWORD oldProtect)
{
    if (oldProtect) *oldProtect = PAGE_READWRITE;
    return mprotect(address, size, prot_from_page(newProtect)) == 0;
}''','''BOOL VirtualProtect(LPVOID address, SIZE_T size, DWORD newProtect, PDWORD oldProtect)
{
    if (oldProtect) *oldProtect = PAGE_READWRITE;
#if defined(__APPLE__) && TARGET_OS_IPHONE
    long n = sysconf(_SC_PAGESIZE);
    if (!address || !size || n <= 0 || (n & (n - 1)) != 0) {
        errno = EINVAL;
        return FALSE;
    }
    uintptr_t page = (uintptr_t)n;
    uintptr_t start = (uintptr_t)address;
    if ((uintptr_t)size > UINTPTR_MAX - start) {
        errno = EINVAL;
        return FALSE;
    }
    uintptr_t end = start + (uintptr_t)size;
    if (end > UINTPTR_MAX - (page - 1u)) {
        errno = EINVAL;
        return FALSE;
    }
    uintptr_t lo = start & ~(page - 1u);
    uintptr_t hi = (end + page - 1u) & ~(page - 1u);
    if (hi <= lo) { errno = EINVAL; return FALSE; }
    /* Xbox 4K protection is coarser on Apple's 16K host pages. */
    return mprotect((void *)lo, (size_t)(hi - lo),
                    prot_from_page(newProtect)) == 0;
#else
    return mprotect(address, size, prot_from_page(newProtect)) == 0;
#endif
}''','B21 mprotect real host page granularity')
    compat.write_text(s)
    mem=root/'port/third_party/xboxrecomp/src/kernel/xbox_memory_layout.c'
    s=mem.read_text()
    s=one(s,'#include <setjmp.h>', '''#include <setjmp.h>
#include <errno.h>
/* Persistent breadcrumbs are recorded in Documents before each risky VM stage.
 * This is not a substitute for memory correctness; it locates the last stage
 * even when LiveContainer terminates the host with no .ips. */
extern void poptst_engine_trace(const char *);
#if defined(__APPLE__)
#include <TargetConditionals.h>
#endif

/* Diagnoses host RAM-mapping failure without fabricating guest memory. */
static char s_poptst_vm_failure[256];
const char *poptst_ios_vm_failure_detail(void) { return s_poptst_vm_failure; }
static void poptst_vm_set_failure(const char *stage, int err, unsigned long code)
{
    snprintf(s_poptst_vm_failure,sizeof(s_poptst_vm_failure),
             "VM %s: errno=%d (%s), Win32=%lu",stage,err,strerror(err),code);
    fprintf(stderr,"PoPTST VM B15 %s\\n",s_poptst_vm_failure);
    poptst_engine_trace(s_poptst_vm_failure);
}''','VM fail metadata')
    s=one(s,'''    g_force_return = getenv("RECOMP_FORCE_RETURN") != NULL;
    DWORD old_protect;''', '''    s_poptst_vm_failure[0] = '\\0';
    g_force_return = getenv("RECOMP_FORCE_RETURN") != NULL;
    DWORD old_protect;''','clear VM fail each boot')
    s=one(s,'''    if (!g_mapping_handle) {
        fprintf(stderr, "xbox_MemoryLayoutInit: CreateFileMapping failed (error %lu)\\n",''', '''    if (!g_mapping_handle) {
        poptst_vm_set_failure("CreateFileMapping(RAM)", errno, GetLastError());
        fprintf(stderr, "xbox_MemoryLayoutInit: CreateFileMapping failed (error %lu)\\n",''','VM file failure detail')
    s=one(s,'''        g_span_base = VirtualAlloc(NULL, g_span_size, MEM_RESERVE, PAGE_NOACCESS);
#if defined(__ANDROID__) || defined(__APPLE__)''', '''        g_span_base = VirtualAlloc(NULL, g_span_size, MEM_RESERVE, PAGE_NOACCESS);
#if defined(__APPLE__) && TARGET_OS_IPHONE
        fprintf(stderr,"PoPTST VM B15: 4GiB PROT_NONE reserve at %p, bytes=%zu errno=%d\\n",
                g_span_base,g_span_size,g_span_base?0:errno);
#endif
#if defined(__ANDROID__) || defined(__APPLE__)''','VM reserve telemetry')
    s=one(s,'''    if (!g_memory_base) {
        fprintf(stderr, "xbox_MemoryLayoutInit: failed to map base view (%zu KB)\\n",''', '''    if (!g_memory_base) {
        poptst_vm_set_failure("MapViewOfFileEx(base RAM)", errno, GetLastError());
        fprintf(stderr, "xbox_MemoryLayoutInit: failed to map base view (%zu KB)\\n",''','VM mmap failure detail')
    # Additional noninvasive checkpoints for the device-only sudden exit.
    # The API writes and fsyncs a small append-only file, never touches
    # unowned VM pages, and contains no synthetic guest execution.
    s=one(s,'    g_mapping_handle = CreateFileMappingA(',
        '    poptst_engine_trace("VM: create file-backed Xbox RAM (64 MiB)");\n    g_mapping_handle = CreateFileMappingA(',
        'trace before guest file mapping')
    s=one(s,'        g_span_base = VirtualAlloc(NULL, g_span_size, MEM_RESERVE, PAGE_NOACCESS);',
        '        poptst_engine_trace("VM: mmap reserve guest 4GiB PROT_NONE");\n        g_span_base = VirtualAlloc(NULL, g_span_size, MEM_RESERVE, PAGE_NOACCESS);',
        'trace reserve start')
    s=one(s,'        if (g_span_base)\n            w32_compat_own_range(g_span_base, g_span_size);',
        '        if (g_span_base) {\n            poptst_engine_trace("VM: 4GiB reserved successfully; registering owned range");\n            w32_compat_own_range(g_span_base, g_span_size);\n        }',
        'trace owned reservation')
    s=one(s,'    g_memory_offset = (uintptr_t)g_memory_base - XBOX_MAP_START;',
        '    poptst_engine_trace("VM: base file mapping succeeded");\n    g_memory_offset = (uintptr_t)g_memory_base - XBOX_MAP_START;',
        'trace mapped base')
    s=one(s,'    /*\n     * Contiguous / physical memory window at 0x80000000.',
        '    poptst_engine_trace("VM: initial guest RAM and XBE sections copied; mapping contiguous memory");\n    /*\n     * Contiguous / physical memory window at 0x80000000.',
        'trace guest ram initialized')
    s=one(s,'    /*\n     * NV2A hardware register aperture at 0xFD000000 (16 MB).',
        '    poptst_engine_trace("VM: contiguous memory prepared; mapping NV2A");\n    /*\n     * NV2A hardware register aperture at 0xFD000000 (16 MB).',
        'trace NV2A start')
    s=one(s,'    /*\n     * MCPX device apertures.',
        '    poptst_engine_trace("VM: NV2A prepared; mapping MCPX and AC97");\n    /*\n     * MCPX device apertures.',
        'trace MCPX start')
    s=one(s,'    /* Flash ROM aperture -- see XBOX_FLASH_BASE for why. */',
        '    poptst_engine_trace("VM: MCPX prepared; mapping Flash ROM");\n    /* Flash ROM aperture -- see XBOX_FLASH_BASE for why. */',
        'trace flash start')
    s=one(s,'    /*\n     * Allocate a page at Xbox kernel address space (0x80010000).',
        '    poptst_engine_trace("VM: flash ROM prepared; preparing fake kernel page");\n    /*\n     * Allocate a page at Xbox kernel address space (0x80010000).',
        'trace kernel start')
    s=one(s,'    /*\n     * Map mirror views of the 64 MB region.',
        '    poptst_engine_trace("VM: kernel/heap prepared; mapping RAM mirrors");\n    /*\n     * Map mirror views of the 64 MB region.',
        'trace mirrors start')
    s=one(s,'    /*\n     * Tiled / write-combined aperture at 0xF0000000.',
        '    poptst_engine_trace("VM: RAM mirrors and extended VMA initialized; tiled GPU alias next");\n    /*\n     * Tiled / write-combined aperture at 0xF0000000.',
        'trace tile start')
    s=one(s,'    xbox_WatchInit();\n    fprintf(stderr, "xbox_MemoryLayoutInit: complete\\n");',
        '    poptst_engine_trace("VM: all mandatory Xbox memory and tile aliases initialized");\n    xbox_WatchInit();\n    fprintf(stderr, "xbox_MemoryLayoutInit: complete\\n");',
        'trace VM complete')
    # For iOS the physical apertures must exist at the guest offset. Treat
    # missing mandatory mappings as errors instead of a future silent fault.
    s=one(s,'''    xbox_WatchInit();
    fprintf(stderr, "xbox_MemoryLayoutInit: complete\\n");''', '''#if defined(__APPLE__) && TARGET_OS_IPHONE
    if (!g_contig_memory || !g_nv2a_memory || !g_mcpx_memory || !g_flash_memory || !g_tiled_view) {
        char failed[120];
        snprintf(failed,sizeof failed,"aperture contig=%d nv2a=%d mcpx=%d flash=%d tiled=%d",
            !!g_contig_memory,!!g_nv2a_memory,!!g_mcpx_memory,!!g_flash_memory,!!g_tiled_view);
        poptst_vm_set_failure(failed,errno,GetLastError());
        return FALSE;
    }
#endif
    xbox_WatchInit();
    fprintf(stderr, "xbox_MemoryLayoutInit: complete\\n");''','fail closed for GPU and southbridge mappings')
    # Fail closed instead of calling __bzero on read-only contiguous memory
    # when a protection reset fails for any reason.
    s=one(s,'''    if (reclaim) {
        DWORD old;
        VirtualProtect((void *)((uintptr_t)result + g_memory_offset), size,
                       PAGE_READWRITE, &old);
    }
    memset((void *)((uintptr_t)result + g_memory_offset), 0, size);''','''    if (reclaim) {
        DWORD old;
#if defined(__APPLE__) && TARGET_OS_IPHONE
        if (!VirtualProtect((void *)((uintptr_t)result + g_memory_offset),
                            size, PAGE_READWRITE, &old)) {
            char detail[192];
            snprintf(detail,sizeof detail,
                     "FATAL CONTIG PROTECT: guest=0x%08X size=0x%X errno=%d",
                     result,size,errno);
            poptst_engine_trace(detail);
            return 0; /* Do not clear a read-only or unowned host page. */
        }
#else
        VirtualProtect((void *)((uintptr_t)result + g_memory_offset),
                       size, PAGE_READWRITE, &old);
#endif
    }
    memset((void *)((uintptr_t)result + g_memory_offset), 0, size);''',
          'B21 reclaimed contiguous protection failure')
    mem.write_text(s)

    # B22: guest 0x808E8014 after B21 faults on an r-- 16 KiB iOS host page.
    # Xbox uses independently protected 4 KiB physical texture suballocations.
    # Relax ONLY the guest contiguous GPU physical READONLY cache hint, not
    # address protections for MMIO, regular RAM, heap or the OS.
    km=root/'port/third_party/xboxrecomp/src/kernel/kernel_memory.c'
    q=km.read_text()
    q=one(q,'#include "kernel.h"','''#include "kernel.h"
#if defined(__APPLE__)
#include <TargetConditionals.h>
#include <errno.h>
#include <stdio.h>
#include "xbox_memory_layout.h"
#endif''','B22 physical protection includes')
    q=one(q,'''VOID __stdcall xbox_MmSetAddressProtect(PVOID BaseAddress, ULONG NumberOfBytes, ULONG NewProtect)
{
    DWORD old_protect;
    VirtualProtect(BaseAddress, NumberOfBytes, xbox_protect_to_win32(NewProtect), &old_protect);
    XBOX_TRACE(XBOX_LOG_MEM, "MmSetAddressProtect(%p, %u, 0x%X)", BaseAddress, NumberOfBytes, NewProtect);
}''','''VOID __stdcall xbox_MmSetAddressProtect(PVOID BaseAddress, ULONG NumberOfBytes, ULONG NewProtect)
{
    DWORD old_protect;
#if defined(__APPLE__) && TARGET_OS_IPHONE
    /* Xbox 4 KiB pages cannot map to separate Darwin 16 KiB permissions.
     * In physical GPU texture arena, READONLY|WRITECOMBINE represents a
     * guest cache hint; denying the whole host page also denies unrelated
     * writable guest blocks. Preserve host RW for this narrow case. */
    const uintptr_t guest_zero = (uintptr_t)xbox_GetMemoryOffset();
    const uintptr_t address = (uintptr_t)BaseAddress;
    if (guest_zero && address >= guest_zero && NumberOfBytes > 0 &&
        (NewProtect & 0xffu) == PAGE_READONLY) {
        const uint64_t guest = (uint64_t)(address - guest_zero);
        if (guest >= 0x80000000ull && guest < 0x84000000ull &&
            (uint64_t)NumberOfBytes <= 0x84000000ull - guest) {
            BOOL ok = VirtualProtect(BaseAddress, NumberOfBytes,
                                     PAGE_READWRITE, &old_protect);
            static unsigned report_count;
            if (__atomic_fetch_add(&report_count, 1u, __ATOMIC_RELAXED) < 24u || !ok) {
                char detail[200];
                snprintf(detail, sizeof detail,
                         "GPU PAGE B22: guest=0x%08X size=0x%X request=0x%X RW=%s errno=%d",
                         (unsigned)guest, (unsigned)NumberOfBytes,
                         (unsigned)NewProtect, ok ? "OK" : "FAILED", ok ? 0 : errno);
                extern void poptst_engine_trace(const char *);
                poptst_engine_trace(detail);
            }
            return;
        }
    }
#endif
    VirtualProtect(BaseAddress, NumberOfBytes, xbox_protect_to_win32(NewProtect), &old_protect);
    XBOX_TRACE(XBOX_LOG_MEM, "MmSetAddressProtect(%p, %u, 0x%X)", BaseAddress, NumberOfBytes, NewProtect);
}''','B22 iOS-only 16KiB GPU page protection policy')
    km.write_text(q)

    print('PASS Build 15: real sparse RAM, aliased file mapping, VM failure telemetry, mandatory apertures')

if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('usage: patch_vm_ios.py <pinned-rePOP-checkout>')
    main(Path(sys.argv[1]).resolve())
