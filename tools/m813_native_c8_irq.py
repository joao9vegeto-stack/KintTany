#!/usr/bin/env python3
"""M8.13: native, template-verified C8 WWS generated irq save/restore AOT.

The C8D774 PM itself writes a 0x130-byte sequence at LS 0x3FEC0 and
a bi $79 at 0x3FFF0. Do not interpret SPU instructions or skip the
interrupt: verify the exact guest-generated template, then run its
fixed semantics with compiled C operations.
"""
import argparse
from pathlib import Path
MARK="ASCENSION_M813_C8_IRQ_NATIVE_V1"

def replace_once(s, needle, repl):
    n=s.count(needle)
    if n!=1:raise RuntimeError(f"M8.13 anchor {needle[:110]!r}: {n}")
    return s.replace(needle,repl,1)

def apply(upstream, repo):
    chan=Path(upstream)/"runtime/spu/spu_channels.c"
    s=chan.read_text()
    assert "ASCENSION_M812_NATIVE_SPU_GAP_V1" in s
    if MARK not in s:
        block=r'''/* ASCENSION_M813_C8_IRQ_NATIVE_V1
 * C8 WWS PM generator at LS 0xA2C/0xA60 and 0xA90/0xAAC writes
 * 19 x 16 bytes (76 instructions) starting at 0x3FEC0. All are
 * stqa r0..r75 or lqa r0..r75, absolute targets 0x3F9C0+16*reg.
 * Generator then writes bi $79 (0x35002780) at 0x3FFF0.
 *
 * This is NOT a guest-instruction interpreter: all bytes are verified
 * against the known NPUA C8 image's two exact templates before touching
 * state, then predetermined native operations perform the copy.
 * [0] seen [1] native saves [2] native restores [3] rejected variants
 * [4] last first word [5] first invalid instruction index
 * [6] last target link [7] last image [8] last suffix word
 */
static volatile uint64_t s_asc_c8_irq[9];
void spu_ascension_reset_c8_irq(void) {
    for(unsigned i=0;i<9;i++)
        __atomic_store_n(&s_asc_c8_irq[i],0,__ATOMIC_RELAXED);
}
void spu_ascension_copy_c8_irq(uint64_t out[9]) {
    if(!out)return;
    for(unsigned i=0;i<9;i++)
        out[i]=__atomic_load_n(&s_asc_c8_irq[i],__ATOMIC_RELAXED);
}
static uint32_t asc_c8_irq_be32(const uint8_t* p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|
           ((uint32_t)p[2]<<8)|((uint32_t)p[3]);
}
int spu_ascension_run_c8_generated_irq(spu_context* ctx) {
    if(!ctx || ctx->image_id!=6 || !ctx->policy_mode ||
       (ctx->pc & SPU_LS_MASK)!=0x3FEC0u)
        return 0;
    __atomic_fetch_add(&s_asc_c8_irq[0],1,__ATOMIC_RELAXED);
    const uint32_t word0=asc_c8_irq_be32(ctx->ls+0x3FEC0);
    const uint32_t term=asc_c8_irq_be32(ctx->ls+0x3FFF0);
    __atomic_store_n(&s_asc_c8_irq[4],word0,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_c8_irq[7],(uint32_t)ctx->image_id,__ATOMIC_RELAXED);
    __atomic_store_n(&s_asc_c8_irq[8],term,__ATOMIC_RELAXED);
    const int saving=word0==UINT32_C(0x20FF3800);
    const int restoring=word0==UINT32_C(0x30FF3800);
    unsigned invalid=76;
    if(!saving && !restoring) invalid=0;
    else if(term!=UINT32_C(0x35002780)) invalid=76;
    else {
        /* SPU RI16 stqa/lqa: each consecutive register increments
         * the instruction word by 0x201 (reg + 1, absolute EA + 16). */
        for(unsigned i=0;i<76;i++){
            const uint32_t word=asc_c8_irq_be32(ctx->ls+0x3FEC0+4*i);
            if(word!=word0+UINT32_C(0x201)*i) {
                invalid=i;
                break;
            }
        }
        if(invalid==76) invalid=UINT32_MAX; /* all words matched */
    }
    if(invalid!=UINT32_MAX) {
        __atomic_fetch_add(&s_asc_c8_irq[3],1,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_c8_irq[5],invalid,__ATOMIC_RELAXED);
        return 0; /* native-only missing AOT fail-closed; no interpreter */
    }
    /* The PM saves r76..r79 separately at 0x3FE80..0x3FEB0.
     * Handle only r0..r75 as the generated program does, preserving
     * the live r79 link. All addresses are fixed and bounded. */
    if(saving) {
        for(unsigned i=0;i<76;i++)
            spu_ls_write128(ctx,0x3F9C0u+16u*i,ctx->gpr[i]);
        __atomic_fetch_add(&s_asc_c8_irq[1],1,__ATOMIC_RELAXED);
    } else {
        for(unsigned i=0;i<76;i++)
            ctx->gpr[i]=spu_ls_read128(ctx,0x3F9C0u+16u*i);
        __atomic_fetch_add(&s_asc_c8_irq[2],1,__ATOMIC_RELAXED);
    }
    /* bi $79: native transfer back to already-lifted C8 policy code. */
    const uint32_t target=ctx->gpr[79]._u32[0] & SPU_LS_MASK & ~3u;
    __atomic_store_n(&s_asc_c8_irq[6],target,__ATOMIC_RELAXED);
    ctx->pc=target;
    g_spu_trampoline_fn=spu_indirect_branch;
    return 1;
}

'''
        s=replace_once(s,"void spu_indirect_branch(spu_context* ctx)\n{",
                       block+"void spu_indirect_branch(spu_context* ctx)\n{")
        hook="""    ctx->pc &= SPU_LS_MASK;
    /* Interrupt-return register restore"""
        s=replace_once(s,hook,"""    ctx->pc &= SPU_LS_MASK;
    /* Match the verified NPUA C8 WWS generated stub before PIC lookup.
     * The static C8 function at this address also calls this same helper. */
    if(ctx->pc==0x3FEC0u && spu_ascension_run_c8_generated_irq(ctx))
        return;
    /* Interrupt-return register restore""")
        chan.write_text(s)
    assert MARK in s and "spu_ascension_run_c8_generated_irq" in s

    # Keep the exact C8 lift byte-for-byte: its manifest authenticates
    # the generated source and must not be invalidated by our runtime fix.
    # The original 0x3FEC0 thunk already calls spu_indirect_branch,
    # now intercepted by our native exact-template executor.
    gen=Path(repo)/"runtime/m789-c8-wws/spu_recomp.c"
    g=gen.read_text()
    old="""void wws_pm_c8d774_spu_func_0003FEC0(spu_context* ctx) {
    ctx->pc = 0x3FEC0u; g_spu_trampoline_fn = spu_indirect_branch; return;
}"""
    if g.count(old)!=1:
        raise RuntimeError("M8.13 exact original C8-generated thunk or source SHA changed")
    print("[PASS] M8.13 C8 exact generated IRQ native-AOT save/restore and fail-closed")

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--upstream",type=Path,required=True)
    a.add_argument("--repo",type=Path,default=Path("."))
    args=a.parse_args();apply(args.upstream,args.repo)
