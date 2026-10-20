/* M7.72: install the owner-local PS3Recomp lift into the upstream dispatch tables. */
#include <pthread.h>
#include <stdint.h>
#include <stddef.h>
#include <string>

#include "ppu/ppu_recomp.h"

extern "C" void ppu_recomp_register(void);
extern "C" void ppu_hle_init(void);
extern "C" void ppu_sysprx_register(void);
extern "C" void ppu_fs_register(void);
extern "C" void ppu_fs_ios_reset_stats(void);
extern "C" void ppu_fs_ios_stats(uint64_t out[4]);
extern "C" void lv2_init_syscalls(void);
extern "C" void ppu_install_thread_trampoline(void);
extern "C" uint64_t ppu_thread_register_main(void);
extern "C" void ppu_resv_register(ppu_context*);
extern "C" void ps3_indirect_call_to(ppu_context*,uint32_t);
extern "C" PPU_THREAD_LOCAL ppu_context* g_active_ctx;
extern "C" ppu_context* volatile g_ppu_main_ctx;
extern "C" uint8_t* vm_base;
extern "C" uint32_t ppu_vm_size;
extern "C" const char* ppu_vfs_root;
/* The generated SPU headers put these declarations after their extern-C
 * block, although their implementations are compiled as C.  Declare the C
 * ABI explicitly here so the final iOS linker resolves the actual exports. */
extern "C" void gowa_spu_0000_at_006B3E00_spu_recomp_register(void);
extern "C" void gowa_spu_0001_at_006C1B00_spu_recomp_register(void);
extern "C" void gowa_spu_0002_at_006CB580_spu_recomp_register(void);
extern "C" void gowa_spu_0003_at_006D5900_spu_recomp_register(void);

static pthread_once_t m772_once = PTHREAD_ONCE_INIT;
static uint32_t m772_initialized;
static uint32_t m772_guest_vm_size;
static uint64_t m772_dispatch_count;
static uint32_t m772_last_guest_pc;
static uint32_t m772_sorted_table = 1;
static uint32_t m772_vfs_root_set;
static std::string m772_vfs_root;
static uint32_t m772_has_ppu(uint32_t pc);

/* Reports should describe the current import attempt instead of leaving
 * counters from an earlier ELF run visible during the next preflight. */
extern "C" void ar_m772_runtime_begin(void)
{
    __atomic_store_n(&m772_initialized, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&m772_guest_vm_size, 0u, __ATOMIC_RELAXED);
    __atomic_store_n(&m772_dispatch_count, UINT64_C(0), __ATOMIC_RELAXED);
    __atomic_store_n(&m772_last_guest_pc, 0u, __ATOMIC_RELAXED);
    __atomic_store_n(&m772_vfs_root_set, 0u, __ATOMIC_RELEASE);
    ppu_fs_ios_reset_stats();
}

static void m772_register_all(void)
{
    for (uint64_t i = 1; i < function_table_count; ++i)
        if (function_table[i - 1].addr >= function_table[i].addr)
            m772_sorted_table = 0;
    ppu_recomp_register();
    ppu_hle_init();
    ppu_sysprx_register();
    ppu_fs_register();
    lv2_init_syscalls();
    ppu_install_thread_trampoline();
    gowa_spu_0000_at_006B3E00_spu_recomp_register();
    gowa_spu_0001_at_006C1B00_spu_recomp_register();
    gowa_spu_0002_at_006CB580_spu_recomp_register();
    gowa_spu_0003_at_006D5900_spu_recomp_register();
    ppu_fs_ios_reset_stats();
}

extern "C" int ar_m772_runtime_init(uint8_t* guest_memory,size_t guest_size,
                                      const char* game_root)
{
    if (!guest_memory || !guest_size || guest_size > UINT32_MAX ||
        !game_root || !*game_root) return -1;
    /* Both runtimes now address the exact PT_LOAD allocation populated by
     * ar_load_elf_image.  The separate 16 MiB graphics probe arena must never
     * be used for guest PPU execution. */
    vm_base = guest_memory;
    ppu_vm_size = (uint32_t)guest_size;
    m772_vfs_root.assign(game_root);
    ppu_vfs_root = m772_vfs_root.c_str();
    ppu_fs_ios_reset_stats();
    __atomic_store_n(&m772_vfs_root_set, 1u, __ATOMIC_RELEASE);
    __atomic_store_n(&m772_dispatch_count, UINT64_C(0), __ATOMIC_RELAXED);
    __atomic_store_n(&m772_last_guest_pc, 0u, __ATOMIC_RELAXED);
    __atomic_store_n(&m772_guest_vm_size,(uint32_t)guest_size,__ATOMIC_RELAXED);
    pthread_once(&m772_once, m772_register_all);
    __atomic_store_n(&m772_initialized, 1u, __ATOMIC_RELEASE);
    return 0;
}

/* Match the PS3Recomp process-entry state before entering the ELF OPD.  The
 * iOS host uses its own ELF/VFS owner, so it cannot call upstream ppu_run(),
 * but the guest CRT still requires the same LV2 thread identity, TLS image,
 * reservation registration and command-line ABI. */
extern "C" int ar_m772_prepare_main(ppu_context* ctx,uint32_t tls_vaddr,
                                     uint32_t tls_filesz,uint32_t tls_memsz,
                                     uint32_t stack_top,uint32_t argv_base)
{
    constexpr uint32_t tls_image = 0x10f00000u;
    constexpr uint32_t tls_tp = tls_image + 0x7000u;
    if (!ctx || !vm_base || !ppu_vm_size || !stack_top || !argv_base ||
        tls_filesz > tls_memsz || tls_memsz > 1024u*1024u ||
        tls_vaddr > ppu_vm_size || tls_filesz > ppu_vm_size - tls_vaddr ||
        tls_memsz > ppu_vm_size - tls_image ||
        argv_base > ppu_vm_size - 24u ||
        stack_top > ppu_vm_size || argv_base >= stack_top)
        return -1;

    ctx->thread_id = ppu_thread_register_main();
    if (!ctx->thread_id) return -2;
    g_ppu_main_ctx = ctx;
    g_active_ctx = ctx;
    ppu_resv_register(ctx);

    ctx->gpr[7] = ctx->thread_id;
    ctx->gpr[8] = tls_vaddr;
    ctx->gpr[9] = tls_filesz;
    ctx->gpr[10] = tls_memsz;
    ctx->gpr[12] = 0x100000u;
    if (tls_memsz) {
        memcpy(vm_base + tls_image, vm_base + tls_vaddr, tls_filesz);
        if (tls_memsz > tls_filesz)
            memset(vm_base + tls_image + tls_filesz, 0, tls_memsz - tls_filesz);
        ctx->gpr[13] = tls_tp;
    }

    /* argc=1; argv[0] is the real disc boot path. PPU pointers occupy the
     * low 32 bits of big-endian 64-bit slots, as in upstream ppu_run(). */
    ctx->gpr[3] = 1;
    ctx->gpr[4] = argv_base;
    ctx->gpr[5] = argv_base + 16u;
    ctx->gpr[6] = 0;
    return 0;
}

extern "C" void ar_m772_unbind_guest_memory(void* guest_memory)
{
    if (!guest_memory || vm_base != guest_memory) return;
    vm_base = nullptr;
    ppu_vm_size = 0;
    __atomic_store_n(&m772_guest_vm_size, 0u, __ATOMIC_RELEASE);
}

extern "C" int ar_m772_dispatch_native(ppu_context* ctx,uint32_t pc)
{
    if (!ctx || !m772_has_ppu(pc)) return 0;
    __atomic_add_fetch(&m772_dispatch_count, UINT64_C(1), __ATOMIC_RELAXED);
    __atomic_store_n(&m772_last_guest_pc, pc, __ATOMIC_RELAXED);
    ps3_indirect_call_to(ctx, pc);
    ctx->cia = ctx->lr;
    return 1;
}

static uint32_t m772_has_ppu(uint32_t pc)
{
    if (!m772_sorted_table) {
        for (uint64_t i = 0; i < function_table_count; ++i)
            if (function_table[i].addr == pc && function_table[i].func) return 1;
        return 0;
    }
    uint64_t lo = 0, hi = function_table_count;
    while (lo < hi) {
        const uint64_t mid = lo + (hi - lo) / 2;
        if (function_table[mid].addr < pc) lo = mid + 1;
        else hi = mid;
    }
    return lo < function_table_count && function_table[lo].addr == pc &&
           function_table[lo].func != nullptr;
}

extern "C" void ar_m772_runtime_attest(uint64_t out[13])
{
    if (!out) return;
    const uint32_t ready = __atomic_load_n(&m772_initialized, __ATOMIC_ACQUIRE);
    /* The UI may poll while runtime_init is registering thousands of entries.
     * Do not inspect the mutable registry until the release/acquire handshake. */
    out[0] = ready ? function_table_count : 0;
    out[1] = ready ? m772_has_ppu(0x0052A740u) : 0;
    out[2] = ready ? m772_has_ppu(0x0052E3F4u) : 0;
    out[3] = ready ? 4 : 0; /* SPU image registrations completed. */
    out[4] = ready;
    out[5] = __atomic_load_n(&m772_dispatch_count, __ATOMIC_RELAXED);
    out[6] = __atomic_load_n(&m772_last_guest_pc, __ATOMIC_RELAXED);
    out[7] = __atomic_load_n(&m772_guest_vm_size, __ATOMIC_RELAXED);
    out[8] = __atomic_load_n(&m772_vfs_root_set, __ATOMIC_ACQUIRE);
    ppu_fs_ios_stats(out + 9);
}
