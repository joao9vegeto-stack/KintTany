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
void *ar_guest_memory_base(void);
size_t ar_guest_memory_capacity(void);
/* Last PS3 guest-VM reservation attempt. failure_stage is zero on success;
 * reservation_kind is 1 for a 4-GiB mmap-anywhere reservation or 3 for a
 * Mach VM anywhere reservation. errno and the base are captured before
 * guest shutdown. */
typedef struct {
    uint32_t attempted;
    uint32_t reservation_kind;
    uint32_t mmap_attempts;
    uint32_t mach_attempts;
    uint32_t failure_stage;
    int32_t failure_errno;
    int32_t last_mach_kern_return;
    uint64_t reservation_base;
} ar_vm_reservation_status;
enum {
    AR_VM_STAGE_NONE=0,
    AR_VM_STAGE_NEEDS_64BIT=1,
    AR_VM_STAGE_ALIGNED_HINT=2,
    AR_VM_STAGE_HINT_RELOCATED=3,
    AR_VM_STAGE_HINT_CLEANUP=4,
    AR_VM_STAGE_FALLBACK_MAP=5,
    AR_VM_STAGE_TRIM=6,
    AR_VM_STAGE_PROTECT_LOW=7,
    AR_VM_STAGE_PROTECT_RSX=8,
    AR_VM_STAGE_PROTECT_STACK=9,
    AR_VM_STAGE_RELEASE=10,
    AR_VM_STAGE_MACH_ALLOCATE=11,
    AR_VM_STAGE_MACH_PROTECT_NONE=12,
    AR_VM_STAGE_MACH_PROTECT_COMMIT=13,
    AR_VM_STAGE_MACH_RELEASE=14
};
void ar_bridge_vm_reservation_status(ar_vm_reservation_status *out);
int ar_register(uint32_t, ar_ppu_fn);
int ar_run(ppu_context *, uint32_t, uint32_t);
int ar_last_error(void);
int ar_bind_import(uint32_t stub,uint32_t nid);
int ar_bind_hle(uint32_t nid,ar_hle_fn handler);
int ar_bind_syscall(uint32_t syscall_number,ar_hle_fn handler);
int ar_guest_syscall(ppu_context*);
void ar_ppc_note_syscall_pc(uint32_t pc);
void ar_ppc_note_barrier(uint32_t pc, uint32_t instruction);
void ar_ppc_note_fp(uint32_t pc, uint32_t instruction);
uint32_t ar_last_missing_syscall(void);
uint32_t ar_last_missing_nid(void);
uint32_t ar_last_unresolved(void);
size_t ar_registered_count(void);
/* M7.17: counts from the actual signed AOT dispatcher, not PPU interpreter.
 * trace_pcs are real registered ARM64 entrypoints, oldest to newest.
 * unique_aot counts distinct registered entries reached within one ar_run. */
/* M7.38: one shared bound for on-device attach and host runtime.
 * Previously the app requested 16,384 but the dispatcher rejected >4,096,
 * causing loader=-38 before any AOT executed. Never remove the bound. */
#define AR_PPC_FALLBACK_MAX_STEPS 16384u
#define AR_AOT_TRACE_PCS 64u
#define AR_AOT_TRIAGE_FIRST 256u
#define AR_AOT_TRIAGE_RUNS 128u
#define AR_FALLBACK_TRACE_PCS 32u
typedef struct {
    uint32_t aot_dispatches, unique_aot, unresolved_pc;
    uint32_t hle_dispatches, max_budget, trace_count;
    uint32_t trace_pcs[AR_AOT_TRACE_PCS];
    /* M7.20: INTERPRETER FALLBACK counts are NEVER included in AOT counts. */
    uint32_t fallback_steps, fallback_last_pc, fallback_last_opcode;
    uint32_t fallback_unsupported_pc, fallback_unsupported_word;
    uint32_t fallback_step_limit;
    /* M7.30 only actual interpreted tail PCs; 32 latest, chronological. */
    uint32_t fallback_trace_count;
    uint32_t fallback_trace_pcs[AR_FALLBACK_TRACE_PCS];
    uint32_t fallback_trace_words[AR_FALLBACK_TRACE_PCS];
    uint32_t fallback_callsite_pc, fallback_call_target; /* M7.25 */
    /* M7.26: actual LV2 syscall IDs, without fake successes. */
    uint32_t lv2_calls, lv2_last_number, lv2_last_pc;
    uint32_t lv2_missing_number, lv2_missing_pc;
    /* M7.27: real fallback-executed memory ordering barriers only. */
    uint32_t eieio_steps, sync_steps, lwsync_steps, isync_steps;
    uint32_t last_barrier_pc;
    /* M7.29 actual PPC fallback FP steps; not native AOT. */
    uint32_t fp_loads,fp_stores,fp_converts,fp_divides,fp_last_pc;
    uint32_t lv2_timezone_completed; /* M7.33: actual iPhone LV2 144 success count */
    /* M7.60: append-only telemetry (no PPC interpretation).
     * First appearances survive a hot loop, and run-length entries keep
     * the last 128 TRANSITIONS rather than just 64 raw dispatches. */
    uint32_t first_count, first_total, first_pcs[AR_AOT_TRIAGE_FIRST];
    uint32_t run_count, run_total;
    uint32_t run_pcs[AR_AOT_TRIAGE_RUNS],run_repetitions[AR_AOT_TRIAGE_RUNS];
    uint32_t stop_previous_aot, stop_cr, stop_xer;
    uint64_t stop_lr, stop_ctr, stop_r1, stop_r2, stop_r3;
    /* M7.64.1 native dispatcher AOT tail edge telemetry. */
    uint32_t tail_count, tail_source, tail_target, tail_target_has_native;
    uint32_t first_unlinked_tail_source, first_unlinked_tail_target;
    /* M7.67: exact pre-shutdown fail source; do not confuse HLE dispatch with missing native PC. */
    uint32_t m767_fail_pc, m767_fail_reason, m767_failed_handler_pc;
    uint32_t m767_hle_calls, m767_hle_stub, m767_hle_nid, m767_hle_success;
    /* M7.68: transport semantics distinct from ordinary linked AOT. */
    uint32_t m768_hle_return_count, m768_hle_return_native, m768_last_hle_return_pc;
    uint32_t m768_tail_hle_lookup_count, m768_tail_hle_found_count;
    uint32_t m768_last_hle_entry_from_tail, m768_last_hle_depth;
    int32_t m767_hle_result;
    uint64_t m767_hle_pre_lr, m767_hle_pre_toc, m767_hle_pre_r3, m767_hle_post_r3;
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
/* All-or-nothing byte fetch for VMX Cell partial vectors. */
int ar_vm_read_bytes(uint64_t,void *,size_t);
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
