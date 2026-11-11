#include "XOWUEConstantPacking.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>

static uint32_t value(uint32_t stage, uint32_t index, uint32_t component)
{
    return 0xA5000000u | (stage << 20u) | (index << 2u) | component;
}

int main(void)
{
    XOWUEGuestDraw draw;
    uint32_t packed[XOWUE_GPU_CONSTANT_WORDS];
    memset(&draw, 0, sizeof(draw));
    memset(packed, 0xCC, sizeof(packed));

    for (uint32_t index = 0; index < 256u; ++index) {
        for (uint32_t component = 0; component < 4u; ++component) {
            draw.constants[index * 4u + component] = value(0u,index,component);
            draw.constants[(256u + index) * 4u + component] = value(1u,index,component);
        }
    }
    for (uint32_t i = 2048u; i < XOWUE_GPU_CONSTANT_WORDS; ++i)
        draw.constants[i] = 0x5A000000u + i;

    draw.vs_const_packed = 1u;
    draw.vs_const_used[0] = UINT64_C(1) << 3u;
    draw.vs_const_used[1] = UINT64_C(1) << (100u - 64u);
    draw.ps_const_packed = 1u;
    draw.ps_const_used[0] = UINT64_C(1) << 2u;
    draw.ps_const_used[3] = UINT64_C(1) << (200u - 192u);

    assert(xowue_prepare_guest_draw_constants(&draw, packed, XOWUE_GPU_CONSTANT_WORDS));
    for (uint32_t c = 0; c < 4u; ++c) {
        assert(packed[c] == value(0u,3u,c));
        assert(packed[4u + c] == value(0u,100u,c));
        assert(packed[256u * 4u + c] == value(1u,2u,c));
        assert(packed[257u * 4u + c] == value(1u,200u,c));
    }
    for (uint32_t i = 2048u; i < XOWUE_GPU_CONSTANT_WORDS; ++i)
        assert(packed[i] == draw.constants[i]);

    // Unpacked stages must retain the original register indices byte-for-byte.
    draw.vs_const_packed = 0u;
    draw.ps_const_packed = 0u;
    assert(xowue_prepare_guest_draw_constants(&draw, packed, XOWUE_GPU_CONSTANT_WORDS));
    assert(memcmp(packed, draw.constants, sizeof(draw.constants)) == 0);
    assert(!xowue_prepare_guest_draw_constants(&draw, packed, XOWUE_GPU_CONSTANT_WORDS - 1u));
    assert(!xowue_prepare_guest_draw_constants(NULL, packed, XOWUE_GPU_CONSTANT_WORDS));
    assert(!xowue_prepare_guest_draw_constants(&draw, NULL, XOWUE_GPU_CONSTANT_WORDS));
    return 0;
}
