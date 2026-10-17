/* M7.15: native AOT for four authentic NPUA80918 instructions at
 * 0x003C4DB4. This is NOT a translator for unknown future instructions. */
#include <stddef.h>
#include <stdint.h>
#include "ppu_bridge.h"

extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define AR_M715_PC UINT32_C(0x003c4db4)
#define AR_M715_NEXT UINT32_C(0x003c4dc4)
#define AR_M715_CA UINT32_C(0x20000000)

int ar_m715_aot_003c4db4(ppu_context *c) {
    if (!c) return AR_BAD_ARGS;

    /* 0x33E40004: addic r31,r4,4 (PPC64 arithmetic, XER.CA). */
    const uint64_t a=c->gpr[4];
    const uint64_t sum=a+UINT64_C(4);
    c->gpr[31]=sum;
    c->xer=(c->xer & ~AR_M715_CA) | ((sum<a)?AR_M715_CA:0u);

    /* 0x60630001: ori r3,r3,1 (does not update CR or XER). */
    c->gpr[3] |= UINT64_C(1);

    /* 0x80C5AE5C: lwz r6,-0x51A4(r5), unsigned BE 32-bit load. */
    const uint64_t ea=c->gpr[5] - UINT64_C(0x51a4);
    const uint32_t word=ar_read32(ea);
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    c->gpr[6]=(uint64_t)word;

    /* 0x93A5AE5C: stw r29,-0x51A4(r5), same address.
     * Strict order: load original value before overwriting it. */
    ar_write32(ea,(uint32_t)c->gpr[29]);
    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;

    c->cia=AR_M715_NEXT;
    return AR_TAIL;
}
int ar_m715_register_fragment(const uint8_t *elf,size_t length) {
    const uint32_t authentic[4]={
        UINT32_C(0x33e40004),UINT32_C(0x60630001),
        UINT32_C(0x80c5ae5c),UINT32_C(0x93a5ae5c)
    };
    uint32_t got[6]={0};
    if (ar_m712_exec_window(elf,length,AR_M715_PC,got)!=0
        ||got[4]!=4u || !(got[5]&1u)) return AR_BAD_ARGS;
    for(unsigned i=0;i<4u;i++)
        if(got[i]!=authentic[i]) return AR_BAD_ARGS;
    return ar_register(AR_M715_PC,ar_m715_aot_003c4db4);
}
