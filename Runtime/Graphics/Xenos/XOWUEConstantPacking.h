// XOWUE shader-stage constant upload contract.
// The translator can rewrite absolute c-register references to packed slots.
// The renderer must mirror that exact per-stage remap before uploading the UBO.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "XOWUEGuestDraw.h"

static inline bool xowue_prepare_guest_draw_constants(
    const XOWUEGuestDraw *draw, uint32_t *destination, size_t destination_words)
{
    if (!draw || !destination || destination_words < XOWUE_GPU_CONSTANT_WORDS)
        return false;

    // Snapshot before writing so an in-place destination is also safe.
    uint32_t source[2048];
    memcpy(source, draw->constants, sizeof(source));
    memcpy(destination, draw->constants, sizeof(draw->constants));

    if (draw->vs_const_packed) {
        uint32_t packed_slot = 0;
        for (uint32_t index = 0; index < 256u; ++index) {
            if ((draw->vs_const_used[index >> 6u] &
                 (UINT64_C(1) << (index & 63u))) == 0u)
                continue;
            memcpy(destination + packed_slot * 4u,
                   source + index * 4u, 4u * sizeof(uint32_t));
            ++packed_slot;
        }
    }

    if (draw->ps_const_packed) {
        const uint32_t stage_base = 256u * 4u;
        uint32_t packed_slot = 0;
        for (uint32_t index = 0; index < 256u; ++index) {
            if ((draw->ps_const_used[index >> 6u] &
                 (UINT64_C(1) << (index & 63u))) == 0u)
                continue;
            memcpy(destination + stage_base + packed_slot * 4u,
                   source + stage_base + index * 4u, 4u * sizeof(uint32_t));
            ++packed_slot;
        }
    }
    return true;
}
