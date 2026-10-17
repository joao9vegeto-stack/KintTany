/* M7.13: 4 authentic, owner-reported NPUA80918 PPC instructions translated
 * to compiled native code. NOT the remainder of the unknown guest routine.
 * Register only after exact executable ELF authentication and signed AOT.
 */
#include <stddef.h>
#include <stdint.h>
#include "ppu_bridge.h"

extern int ar_m712_exec_window(const uint8_t *, size_t, uint32_t, uint32_t[6]);

#define AR_M713_GUEST_PC   UINT32_C(0x003c4d94)
#define AR_M713_GUEST_NEXT UINT32_C(0x003c4da4)
#define AR_M713_XER_CA    UINT32_C(0x20000000)

/* PowerPC64 arithmetic carry-out, not merely a signed overflow flag.
 * XER.SO/OV and CR are deliberately preserved. */
static uint64_t ar_m713_add_carry(ppu_context *c, uint64_t lhs, uint64_t rhs) {
    const unsigned __int128 sum = (unsigned __int128)lhs + rhs;
    const uint32_t carry = (sum >> 64) ? AR_M713_XER_CA : 0u;
    c->xer = (c->xer & ~AR_M713_XER_CA) | carry;
    return (uint64_t)sum;
}

int ar_m713_aot_003c4d94(ppu_context *c) {
    if (!c) return AR_BAD_ARGS;
    /* addc r3,r30,r31 (0x7c7ef814) */
    c->gpr[3] = ar_m713_add_carry(c, c->gpr[30], c->gpr[31]);
    /* addis r5,r0,0x0085 (0x3ca00085) */
    c->gpr[5] = UINT64_C(0x00850000);
    /* addic r3,r3,-4 (0x3063fffc) */
    c->gpr[3] = ar_m713_add_carry(c, c->gpr[3], UINT64_MAX - UINT64_C(3));
    /* addic r4,r29,64 (0x309d0040) */
    c->gpr[4] = ar_m713_add_carry(c, c->gpr[29], UINT64_C(64));
    /* No branch in the authenticated four-instruction window. */
    c->cia = AR_M713_GUEST_NEXT;
    return AR_TAIL;
}

int ar_m713_register_fragment(const uint8_t *elf, size_t length) {
    uint32_t words[6] = {0};
    static const uint32_t expected[4] = {
        UINT32_C(0x7c7ef814), UINT32_C(0x3ca00085),
        UINT32_C(0x3063fffc), UINT32_C(0x309d0040)
    };
    if (ar_m712_exec_window(elf, length, AR_M713_GUEST_PC, words) != 0 ||
        words[4] != 4u || !(words[5] & 1u)) return AR_BAD_ARGS;
    for (size_t i = 0; i < 4; ++i)
        if (words[i] != expected[i]) return AR_BAD_ARGS;
    return ar_register(AR_M713_GUEST_PC, ar_m713_aot_003c4d94);
}
