#!/usr/bin/env python3
"""M8.12: native SPURS2 32-WID policy dispatch and missing AOT SPU evidence."""
from pathlib import Path
import argparse
def change(s, old, new):
    n=s.count(old)
    if n!=1:raise RuntimeError(f"anchor count {n}: {old[:120]}")
    return s.replace(old,new,1)
def patch(root):
    p=Path(root)/"runtime/spu/spurs_policy.c"
    s=p.read_text()
    if "ASCENSION_M812_SPURS2_POLICY_32_V1" not in s:
        # ps3recomp-0020-spurs2-32-workloads.patch ALREADY widens these;
        # never reapply its source hunks or misdiagnose the unpatched pin.
        for required in ("#define SPURS_PM_MAX_WKL 32",
                         "workload_users[SPURS_PM_MAX_WKL]",
                         "slots[SPURS_PM_MAX_WKL][6]",
                         "if (wid >= SPURS_PM_MAX_WKL) return -1;",
                         "for (unsigned w = 0; w < SPURS_PM_MAX_WKL; w++)"):
            assert required in s, "M7.84 SPURS2 32-WID prerequisite missing: " + required

        decl="""/* ASCENSION_M812_SPURS2_POLICY_32_V1
 * Real native policy execution, not just scheduler acceptance.
 * [0] upper calls [1] slots allocated [2] native PM returns
 * [3] native PM error returns [4] early rejects [5] last wid
 * [6] last LS PC [7] image ID [8] last return code [9] last lane
 */
static volatile uint64_t s_asc_upper_policy[10];
void spu_ascension_reset_upper_policy(void) {
    for(unsigned i=0;i<10;i++)
        __atomic_store_n(&s_asc_upper_policy[i],0,__ATOMIC_RELAXED);
}
void spu_ascension_copy_upper_policy(uint64_t out[10]) {
    if(!out)return;
    for(unsigned i=0;i<10;i++)
        out[i]=__atomic_load_n(&s_asc_upper_policy[i],__ATOMIC_RELAXED);
}

"""
        s=change(s,"int spu_run_policy_module(spu_lifted_entry_fn entry, int image_id,",
                 decl+"int spu_run_policy_module(spu_lifted_entry_fn entry, int image_id,")
        s=change(s,"""    if (!entry || !pm_host || !pm_size || pm_size > SPU_LS_SIZE - 0xA00)
        return -1;""","""    if(wid>=16)__atomic_fetch_add(&s_asc_upper_policy[0],1,__ATOMIC_RELAXED);
    if (!entry || !pm_host || !pm_size || pm_size > SPU_LS_SIZE - 0xA00) {
        if(wid>=16)__atomic_fetch_add(&s_asc_upper_policy[4],1,__ATOMIC_RELAXED);
        return -1;
    }""")
        s=change(s,"""    if (wid >= SPURS_PM_MAX_WKL || spu_num >= 6) return -1;
    struct PmSlot* resident = policy_slot(spurs_ea, wid, spu_num);
    if (!resident) return -1;""","""    if (wid >= SPURS_PM_MAX_WKL || spu_num >= 6) {
        if(wid>=16)__atomic_fetch_add(&s_asc_upper_policy[4],1,__ATOMIC_RELAXED);
        return -1;
    }
    struct PmSlot* resident = policy_slot(spurs_ea, wid, spu_num);
    if (!resident) {
        if(wid>=16)__atomic_fetch_add(&s_asc_upper_policy[4],1,__ATOMIC_RELAXED);
        return -1;
    }
    if(wid>=16) {
        __atomic_fetch_add(&s_asc_upper_policy[1],1,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[5],wid,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[7],(uint32_t)image_id,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[9],spu_num,__ATOMIC_RELAXED);
    }""")
        s=change(s,"""    int result = g_spurs_pm_exited ? 0 : -2;
    policy_slot_release(resident);
    return result;""","""    int result = g_spurs_pm_exited ? 0 : -2;
    if(wid>=16) {
        __atomic_fetch_add(&s_asc_upper_policy[2],1,__ATOMIC_RELAXED);
        if(result)__atomic_fetch_add(&s_asc_upper_policy[3],1,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[6],(uint32_t)ctx->pc & SPU_LS_MASK,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[8],(uint32_t)result,__ATOMIC_RELAXED);
    }
    policy_slot_release(resident);
    return result;""")
        p.write_text(s)
    assert "#define SPURS_PM_MAX_WKL 32" in s and "slots[SPURS_PM_MAX_WKL][6]" in s
    ch=Path(root)/"runtime/spu/spu_channels.c"
    s=ch.read_text()
    if "ASCENSION_M812_NATIVE_SPU_GAP_V1" not in s:
        api="""/* ASCENSION_M812_NATIVE_SPU_GAP_V1
 * Last guest SPU target with no matching native AOT/PIC function.
 * [0] count [1] nonzero target [2] zero target [3] last LS PC
 * [4] opcode [5] image [6] resident overlay [7] LS LR
 * [8] resident task [9] policy mode
 */
static volatile uint64_t s_asc_native_gap[10];
void spu_ascension_reset_native_gap(void) {
    for(unsigned i=0;i<10;i++)
        __atomic_store_n(&s_asc_native_gap[i],0,__ATOMIC_RELAXED);
}
void spu_ascension_copy_native_gap(uint64_t out[10]) {
    if(!out)return;
    for(unsigned i=0;i<10;i++)
        out[i]=__atomic_load_n(&s_asc_native_gap[i],__ATOMIC_RELAXED);
}
static void asc_native_gap_note(const spu_context* ctx) {
    uint32_t pc=ctx->pc & SPU_LS_MASK & ~3u;
    uint32_t w=0;
    if(pc <= SPU_LS_SIZE-4)
        for(unsigned i=0;i<4;i++)w=(w<<8)|ctx->ls[pc+i];
    __atomic_fetch_add(&s_asc_native_gap[0],1,__ATOMIC_RELAXED);
    __atomic_fetch_add(&s_asc_native_gap[w?1:2],1,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_native_gap[3],pc,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_native_gap[4],w,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_native_gap[5],(uint32_t)ctx->image_id,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_native_gap[6],(uint32_t)ctx->resident_ovl,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_native_gap[7],ctx->gpr[0]._u32[0]&SPU_LS_MASK,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_native_gap[8],(uint32_t)ctx->resident_task,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_native_gap[9],(uint32_t)ctx->policy_mode,__ATOMIC_RELAXED);
}
"""
        s=change(s,"void spu_indirect_branch(spu_context* ctx)",api+"\nvoid spu_indirect_branch(spu_context* ctx)")
        s=change(s,"""    if (spu_smc_microstep(ctx))
        return;""","""    asc_native_gap_note(ctx);
    /* The old unconditional micro-interpreter violated strict native AOT. */
    if (!getenv("ASCENSION_SPU_NATIVE_ONLY") && spu_smc_microstep(ctx))
        return;""")
        ch.write_text(s)
    assert "ASCENSION_M812_NATIVE_SPU_GAP_V1" in s
    print("[PASS] M8.12 32-WID true native policy and unlifted SPU target evidence")
if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("--upstream",type=Path,required=True)
    patch(a.parse_args().upstream)
