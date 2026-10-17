/* AscensionRecomp M7.16: authentic 15-instruction PPC64/BE owner trace
 * statically compiled to ARM64. No fallback interpreter, guessed guest code,
 * or claim that a graphics or game frame has been submitted.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"

extern int ar_m712_exec_window(const uint8_t *,size_t,uint32_t,uint32_t[6]);
#define PC_BEGIN  UINT32_C(0x003c4dc4)
#define PC_BRANCH UINT32_C(0x003c4dfc)
#define PC_NEXT   UINT32_C(0x003c4e00)
#define PC_TAKEN  UINT32_C(0x003c4e14)
#define XER_CA    UINT32_C(0x20000000)
#define XER_SO    UINT32_C(0x80000000)

int ar_m716_aot_003c4dc4(ppu_context *c) {
    if (!c) return AR_BAD_ARGS;

    /* rldicl r31,r31,0,32: zero-extend low 32 bits */
    c->gpr[31] = (uint64_t)(uint32_t)c->gpr[31];
    /* stw r6,12(r29); stw r4,20(r29); stw r3,0(r4) */
    ar_write32(c->gpr[29] + UINT64_C(12),(uint32_t)c->gpr[6]);
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    ar_write32(c->gpr[29] + UINT64_C(20),(uint32_t)c->gpr[4]);
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    ar_write32(c->gpr[4],(uint32_t)c->gpr[3]);
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;

    /* lwz r5,24(r29); addis r4,0,0x009c; stw r3,0(r5) */
    c->gpr[5]=(uint64_t)ar_read32(c->gpr[29] + UINT64_C(24));
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    c->gpr[4]=UINT64_C(0x009c0000);
    ar_write32(c->gpr[5],(uint32_t)c->gpr[3]);
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;

    /* lwz r3,24(r29); stw r31,4(r29); stw r31,8(r29) */
    c->gpr[3]=(uint64_t)ar_read32(c->gpr[29] + UINT64_C(24));
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    ar_write32(c->gpr[29] + UINT64_C(4),(uint32_t)c->gpr[31]);
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    ar_write32(c->gpr[29] + UINT64_C(8),(uint32_t)c->gpr[31]);
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;

    /* subfc r30,r31,r3: unsigned 64-bit RB - RA, CA=no borrow. */
    const uint64_t ra=c->gpr[31],rb=c->gpr[3];
    c->gpr[30]=rb-ra;
    c->xer=(c->xer & ~XER_CA) | (rb>=ra ? XER_CA : 0u);

    /* lbz r3,0x1780(r4); rldicl r30,r30,0,32 */
    c->gpr[3]=(uint64_t)ar_read8(c->gpr[4] + UINT64_C(0x1780));
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    c->gpr[30]=(uint64_t)(uint32_t)c->gpr[30];

    /* cmpwi cr0,r3,0: signed low-32 comparison; include XER.SO.
     * cmpwi changes CR0 only, NOT XER.CA.
     * beq 0x003c4e14 tests CR0[EQ]; otherwise falls to 0x003c4e00.
     */
    const int32_t cmp=(int32_t)(uint32_t)c->gpr[3];
    const uint32_t cc=(cmp<0 ? UINT32_C(0x80000000) :
                      cmp>0 ? UINT32_C(0x40000000) :
                              UINT32_C(0x20000000)) |
                      ((c->xer & XER_SO) ? UINT32_C(0x10000000):0u);
    c->cr=(c->cr & UINT32_C(0x0fffffff)) | cc;
    c->cia=(c->cr & UINT32_C(0x20000000)) ? PC_TAKEN:PC_NEXT;
    return AR_TAIL;
}

/* Owner's real device reported all 15 words from executable PT_LOAD.
 * The code is linked as ARM64, but registered ONLY if exact ELF matches,
 * alongside the existing whole-ELF SHA-256 owner AOT gate.
 */
int ar_m716_register_block(const uint8_t *elf,size_t length) {
    static const uint32_t words[15]={
        UINT32_C(0x7bff0020),UINT32_C(0x90dd000c),
        UINT32_C(0x909d0014),UINT32_C(0x90640000),
        UINT32_C(0x80bd0018),UINT32_C(0x3c80009c),
        UINT32_C(0x90650000),UINT32_C(0x807d0018),
        UINT32_C(0x93fd0004),UINT32_C(0x93fd0008),
        UINT32_C(0x7fdf1810),UINT32_C(0x88641780),
        UINT32_C(0x7bde0020),UINT32_C(0x2c030000),
        UINT32_C(0x41820018)
    };
    for(unsigned i=0;i<15u;i+=4u){
        uint32_t actual[6]={0};
        if(ar_m712_exec_window(elf,length,PC_BEGIN+4u*i,actual)!=0
           || !(actual[5]&1u) || actual[4]<((15u-i)<4u ? 15u-i:4u))
           return AR_BAD_ARGS;
        for(unsigned j=0;j<actual[4] && j<15u-i;j++)
            if(actual[j]!=words[i+j]) return AR_BAD_ARGS;
    }
    return ar_register(PC_BEGIN,ar_m716_aot_003c4dc4);
}

/* Read-only branch inventory: the two successors must be derived from
 * authentic executable PPC word 0x41820018 (BEQ +24) at 0x003C4DFC.
 * No execution of either unexplored target occurs here.
 */
int ar_m716_verified_successors(const uint8_t *elf,size_t len,
                                 uint32_t out[2]){
    if(!out)return AR_BAD_ARGS;
    out[0]=0u;out[1]=0u;
    uint32_t word[6]={0};
    if(ar_m712_exec_window(elf,len,PC_BRANCH,word)!=0 ||
       word[4]<1u || word[0]!=UINT32_C(0x41820018) ||
       !(word[5]&1u)) return AR_BAD_ARGS;
    out[0]=PC_NEXT;
    out[1]=PC_TAKEN;
    return AR_OK;
}
