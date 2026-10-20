/* M7.72: install the owner-local PS3Recomp lift into the upstream dispatch tables. */
#include <pthread.h>
#include <stdint.h>
#include <stddef.h>

#include "ppu/ppu_recomp.h"

extern "C" void ppu_recomp_register(void);
extern "C" void ppu_hle_init(void);
extern "C" void ppu_sysprx_register(void);
extern "C" void ppu_fs_register(void);
extern "C" void lv2_init_syscalls(void);
extern "C" void ppu_install_thread_trampoline(void);
extern "C" void ps3_indirect_call_to(ppu_context*,uint32_t);
extern "C" uint8_t* vm_base;
extern "C" uint32_t ppu_vm_size;
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
static uint32_t m772_has_ppu(uint32_t pc);

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
}

extern "C" int ar_m772_runtime_init(uint8_t* guest_memory,size_t guest_size)
{
    if (!guest_memory || !guest_size || guest_size > UINT32_MAX) return -1;
    /* Both runtimes now address the exact PT_LOAD allocation populated by
     * ar_load_elf_image.  The separate 16 MiB graphics probe arena must never
     * be used for guest PPU execution. */
    vm_base = guest_memory;
    ppu_vm_size = (uint32_t)guest_size;
    __atomic_store_n(&m772_guest_vm_size,(uint32_t)guest_size,__ATOMIC_RELAXED);
    pthread_once(&m772_once, m772_register_all);
    __atomic_store_n(&m772_initialized, 1u, __ATOMIC_RELEASE);
    return 0;
}

extern "C" void ar_m772_unbind_guest_memory(void* guest_memory)
{
    if (!guest_memory || vm_base != guest_memory) return;
    vm_base = nullptr;
    ppu_vm_size = 0;
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

extern "C" void ar_m772_runtime_attest(uint64_t out[8])
{
    if (!out) return;
    out[0] = function_table_count;
    out[1] = m772_has_ppu(0x0052A740u);
    out[2] = m772_has_ppu(0x0052E3F4u);
    out[3] = 4; /* SPU image registration calls executed above. */
    out[4] = __atomic_load_n(&m772_initialized, __ATOMIC_ACQUIRE);
    out[5] = __atomic_load_n(&m772_dispatch_count, __ATOMIC_RELAXED);
    out[6] = __atomic_load_n(&m772_last_guest_pc, __ATOMIC_RELAXED);
    out[7] = __atomic_load_n(&m772_guest_vm_size, __ATOMIC_RELAXED);
}
