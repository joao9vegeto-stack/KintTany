/* AscensionRecomp: single-threaded test-only PPU AOT dispatcher. */
#ifndef AR_PPU_BRIDGE_H
#define AR_PPU_BRIDGE_H
#include <stdint.h>
#include <stddef.h>
#include "ppu_context.h"
#ifdef __cplusplus
extern "C" {
#endif
enum { AR_OK=0, AR_TAIL=1, AR_BAD_ARGS=-1, AR_MEM_FAULT=-2,
       AR_UNRESOLVED=-3, AR_BUDGET=-4, AR_DEPTH=-5, AR_DUPLICATE=-6,
       AR_NO_MEMORY=-7, AR_MISSING_HLE=-8, AR_HLE_FAILURE=-9, AR_MISSING_LV2=-10, AR_LV2_FAILURE=-11,
       AR_PPC_UNSUPPORTED=-12, AR_PPC_LIMIT=-13 };
typedef int (*ar_ppu_fn)(ppu_context *);
typedef int (*ar_hle_fn)(ppu_context *);
int ar_bridge_init(size_t);
void ar_bridge_shutdown(void);
int ar_register(uint32_t, ar_ppu_fn);
int ar_run(ppu_context *, uint32_t, uint32_t);
int ar_last_error(void);
int ar_bind_import(uint32_t stub,uint32_t nid);
int ar_bind_hle(uint32_t nid,ar_hle_fn handler);
int ar_bind_syscall(uint32_t syscall_number,ar_hle_fn handler);
int ar_guest_syscall(ppu_context*);
uint32_t ar_last_missing_syscall(void);
uint32_t ar_last_missing_nid(void);
uint32_t ar_last_unresolved(void);
size_t ar_registered_count(void);
/* M7.17: counts from the actual signed AOT dispatcher, not PPU interpreter.
 * trace_pcs are real registered ARM64 entrypoints, oldest to newest.
 * unique_aot counts distinct registered entries reached within one ar_run. */
#define AR_AOT_TRACE_PCS 64u
typedef struct {
    uint32_t aot_dispatches, unique_aot, unresolved_pc;
    uint32_t hle_dispatches, max_budget, trace_count;
    uint32_t trace_pcs[AR_AOT_TRACE_PCS];
    /* M7.20: INTERPRETER FALLBACK counts are NEVER included in AOT counts. */
    uint32_t fallback_steps, fallback_last_pc, fallback_last_opcode;
    uint32_t fallback_unsupported_pc, fallback_unsupported_word;
    uint32_t fallback_step_limit;
    uint32_t fallback_callsite_pc, fallback_call_target; /* M7.25 */
} ar_aot_trace;
void ar_trace_snapshot(ar_aot_trace *out);
/* Experimental signed non-JIT fallback. Attach the exact owner ELF ONLY
 * after its SHA-256 was verified by the private AOT installer. Owner of ELF
 * memory must keep it alive through ar_run; bridge never owns these bytes. */
typedef int (*ar_ppc_fallback_fn)(ppu_context*,const uint8_t*,size_t,
                                    uint32_t,uint32_t*);
int ar_ppc_fallback_attach(const uint8_t *elf,size_t len,uint32_t max_steps,
                           ar_ppc_fallback_fn evaluator);
/* Internal single-step evaluator; public only for synthetic tests. */
void ar_ppc_note_failed_call(uint32_t callsite,uint32_t target);
int ar_ppc_fallback_step(ppu_context *c,const uint8_t *elf,size_t len,
                         uint32_t pc,uint32_t *opcode);

/* High mapped guest virtual pages; ownership managed by ppu_mmapper. */
int ar_vm_external_map(uint32_t guest_va,uint8_t *data,size_t length);
int ar_vm_external_unmap(uint32_t guest_va);
int ar_vm_load(uint64_t,const void *,size_t);
int ar_vm_zero(uint64_t,size_t);
uint8_t ar_read8(uint64_t); uint16_t ar_read16(uint64_t);
uint32_t ar_read32(uint64_t); uint64_t ar_read64(uint64_t);
void ar_write8(uint64_t,uint8_t); void ar_write16(uint64_t,uint16_t);
void ar_write32(uint64_t,uint32_t); void ar_write64(uint64_t,uint64_t);
int ar_guest_call(ppu_context *,uint64_t);
#ifdef __cplusplus
}
#endif
#endif
