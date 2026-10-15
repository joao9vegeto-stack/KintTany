#include "ppu_thread_services.h"
/* sysPrxForUser 0x350D454E: sys_ppu_thread_get_id(vm::ptr<u64> id)
 * Store the CURRENT guest thread id, never a hardcoded fake thread 1.
 * Tests require an explicit nonzero registered context identity. */
int ar_sys_ppu_thread_get_id(ppu_context *ctx) {
    if (!ctx || !ctx->thread_id || !ctx->gpr[3] ||
        ctx->gpr[3] > UINT32_MAX - 7u)
        return AR_BAD_ARGS;
    ar_write64(ctx->gpr[3], ctx->thread_id);
    if (ar_last_error() != AR_OK) return AR_MEM_FAULT;
    ctx->gpr[3] = 0;
    return AR_OK;
}
