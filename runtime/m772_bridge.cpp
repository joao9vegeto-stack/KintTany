/* M7.72: install the owner-local PS3Recomp lift into the upstream dispatch tables. */
#include <pthread.h>
#include <stdint.h>

#include "ppu/ppu_recomp.h"
#include "spu/spu_0000_at_006B3E00/spu_recomp.h"
#include "spu/spu_0001_at_006C1B00/spu_recomp.h"
#include "spu/spu_0002_at_006CB580/spu_recomp.h"
#include "spu/spu_0003_at_006D5900/spu_recomp.h"

extern "C" void ppu_recomp_register(void);
extern "C" void ppu_hle_init(void);
extern "C" void ppu_sysprx_register(void);
extern "C" void ppu_fs_register(void);
extern "C" void lv2_init_syscalls(void);

static pthread_once_t m772_once = PTHREAD_ONCE_INIT;

static void m772_register_all(void)
{
    ppu_recomp_register();
    ppu_hle_init();
    ppu_sysprx_register();
    ppu_fs_register();
    lv2_init_syscalls();
    gowa_spu_0000_at_006B3E00_spu_recomp_register();
    gowa_spu_0001_at_006C1B00_spu_recomp_register();
    gowa_spu_0002_at_006CB580_spu_recomp_register();
    gowa_spu_0003_at_006D5900_spu_recomp_register();
}

static uint32_t m772_has_ppu(uint32_t pc)
{
    for (uint64_t i = 0; i < function_table_count; ++i)
        if (function_table[i].addr == pc && function_table[i].func)
            return 1;
    return 0;
}

extern "C" void ar_m772_runtime_attest(uint64_t out[8])
{
    if (!out) return;
    pthread_once(&m772_once, m772_register_all);
    out[0] = function_table_count;
    out[1] = m772_has_ppu(0x0052A740u);
    out[2] = m772_has_ppu(0x0052E3F4u);
    out[3] = 4; /* SPU image registration calls executed above. */
    out[4] = 1; /* registry initializer ran once. */
    out[5] = 0; /* no guest code is run by this registration probe. */
    out[6] = 0;
    out[7] = 0;
}
