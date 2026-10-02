#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int emulate(uint32_t insn, uintptr_t rw_addr, uint64_t gpr[29])
{
    unsigned rs, rt, size, width, kind;
    uint32_t family = insn & 0x3f20fc00u;
    uint64_t src, old = 0;

    switch (family)
    {
    case 0x38200000u: kind = 0; break;
    case 0x38201000u: kind = 1; break;
    case 0x38202000u: kind = 2; break;
    case 0x38203000u: kind = 3; break;
    default: return 0;
    }

    rs = (insn >> 16) & 31;
    rt = insn & 31;
    size = (insn >> 30) & 3;
    width = 1u << size;

    if ((rs >= 29 && rs != 31) || (rt >= 29 && rt != 31)) return 0;
    if (!rw_addr || (rw_addr & (width - 1))) return 0;
    src = rs == 31 ? 0 : gpr[rs];

#define RMW_CASE(type) do {                                                   \
        type *ptr = (type *)rw_addr;                                          \
        type val = (type)src;                                                 \
        type seen;                                                            \
        switch (kind)                                                         \
        {                                                                     \
        case 0: seen = __atomic_fetch_add(ptr, val, __ATOMIC_SEQ_CST); break; \
        case 1: seen = __atomic_fetch_and(ptr, (type)~val,                    \
                                          __ATOMIC_SEQ_CST); break;            \
        case 2: seen = __atomic_fetch_xor(ptr, val, __ATOMIC_SEQ_CST); break; \
        default: seen = __atomic_fetch_or(ptr, val,                           \
                                          __ATOMIC_SEQ_CST); break;            \
        }                                                                     \
        old = seen;                                                           \
    } while (0)

    switch (size)
    {
    case 0: RMW_CASE(uint8_t);  break;
    case 1: RMW_CASE(uint16_t); break;
    case 2: RMW_CASE(uint32_t); break;
    default: RMW_CASE(uint64_t); break;
    }
#undef RMW_CASE

    if (rt != 31) gpr[rt] = old;
    return 1;
}

static uint32_t op(unsigned family, unsigned size, unsigned rs, unsigned rt)
{
    return family | (size << 30) | (rs << 16) | (3u << 5) | rt;
}

static uint64_t mask_for_width(unsigned size)
{
    switch (size) {
    case 0: return UINT8_MAX;
    case 1: return UINT16_MAX;
    case 2: return UINT32_MAX;
    default: return UINT64_MAX;
    }
}

static void run_family(unsigned family, unsigned kind)
{
    for (unsigned size = 0; size < 4; ++size) {
        _Alignas(8) uint64_t mem = 0x0full;
        uint64_t gpr[29] = {0};
        uint64_t m = mask_for_width(size);
        uint64_t src = 3;
        uint64_t expected;
        gpr[1] = src;

        switch (kind) {
        case 0: expected = (0x0f + src) & m; break;
        case 1: expected = 0x0f & (~src & m); break;
        case 2: expected = (0x0f ^ src) & m; break;
        default: expected = (0x0f | src) & m; break;
        }

        assert(emulate(op(family, size, 1, 2), (uintptr_t)&mem, gpr) == 1);
        assert((mem & m) == expected);
        assert(gpr[2] == 0x0f);
    }
}

int main(void)
{
    _Alignas(8) uint64_t cell = 0;
    uint64_t gpr[29] = {0};

    cell = 7;
    gpr[21] = 5;
    assert(emulate(0xb8f50314u, (uintptr_t)&cell, gpr) == 1);
    assert((uint32_t)cell == 12);
    assert(gpr[20] == 7);

    memset(gpr, 0, sizeof(gpr));
    cell = 11;
    gpr[4] = 3;
    assert(emulate(0xb8e40304u, (uintptr_t)&cell, gpr) == 1);
    assert((uint32_t)cell == 14);
    assert(gpr[4] == 11);

    run_family(0x38200000u, 0);
    run_family(0x38201000u, 1);
    run_family(0x38202000u, 2);
    run_family(0x38203000u, 3);

    memset(gpr, 0, sizeof(gpr));
    cell = 9;
    gpr[1] = 2;
    assert(emulate(op(0x38200000u, 2, 1, 31), (uintptr_t)&cell, gpr) == 1);
    assert((uint32_t)cell == 11);

    memset(gpr, 0, sizeof(gpr));
    cell = 13;
    assert(emulate(op(0x38200000u, 2, 31, 2), (uintptr_t)&cell, gpr) == 1);
    assert((uint32_t)cell == 13);
    assert(gpr[2] == 13);

    {
        _Alignas(8) unsigned char bytes[16] = {0};
        uint32_t before;
        memcpy(bytes + 1, "\x07\x00\x00\x00", 4);
        memcpy(&before, bytes + 1, 4);
        memset(gpr, 0, sizeof(gpr));
        gpr[1] = 1;
        assert(emulate(op(0x38200000u, 2, 1, 2), (uintptr_t)(bytes + 1), gpr) == 0);
        {
            uint32_t after;
            memcpy(&after, bytes + 1, 4);
            assert(after == before);
        }
    }

    cell = 7;
    memset(gpr, 0, sizeof(gpr));
    assert(emulate(op(0x38200000u, 2, 29, 2), (uintptr_t)&cell, gpr) == 0);
    assert(emulate(op(0x38200000u, 2, 30, 2), (uintptr_t)&cell, gpr) == 0);
    assert(emulate(op(0x38200000u, 2, 1, 29), (uintptr_t)&cell, gpr) == 0);
    assert(emulate(op(0x38200000u, 2, 1, 30), (uintptr_t)&cell, gpr) == 0);
    assert(emulate(0xc80afec9u, (uintptr_t)&cell, gpr) == 0);

    assert((0xb8f50314u & 0x3f20fc00u) == 0x38200000u);
    assert((0xb8e40304u & 0x3f20fc00u) == 0x38200000u);
    assert((0xc80afec9u & 0x3f20fc00u) != 0x38200000u);

    puts("LSE RMW probe OK: exact LDADDAL opcodes + all families/widths + guards");
    return 0;
}
