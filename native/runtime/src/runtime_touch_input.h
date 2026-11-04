// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <stdint.h>

/*
 * Cross-thread state shared by the UIKit touch overlay and the guest pad sampler.
 * A single UI-thread writer publishes the current buttons and all four stick bytes
 * as one 64-bit word. Press edges are latched until a guest read consumes them,
 * so a tap shorter than the game's polling interval is still observed once.
 */
typedef struct {
    uint64_t state;
    uint32_t pressed;
} Gow3TouchInput;

typedef struct {
    uint32_t buttons;
    uint32_t pressed;
    uint32_t sticks;
} Gow3TouchSnapshot;

#define GOW3_TOUCH_CENTERED_STICKS UINT32_C(0x80808080)

static inline void gow3_touch_input_init(Gow3TouchInput *input) {
    __atomic_store_n(&input->state, (uint64_t)GOW3_TOUCH_CENTERED_STICKS << 32, __ATOMIC_RELAXED);
    __atomic_store_n(&input->pressed, 0, __ATOMIC_RELAXED);
}

/* Call from the single UIKit writer thread. */
static inline void gow3_touch_input_publish(Gow3TouchInput *input, uint32_t buttons, uint32_t sticks) {
    const uint64_t previous = __atomic_load_n(&input->state, __ATOMIC_RELAXED);
    const uint32_t new_presses = buttons & ~(uint32_t)previous;
    const uint64_t next = ((uint64_t)sticks << 32) | buttons;
    __atomic_store_n(&input->state, next, __ATOMIC_RELEASE);
    if (new_presses) {
        __atomic_fetch_or(&input->pressed, new_presses, __ATOMIC_RELEASE);
    }
}

/* A guest poll consumes pending press edges exactly once and gets a coherent axes/buttons snapshot. */
static inline Gow3TouchSnapshot gow3_touch_input_read(Gow3TouchInput *input) {
    const uint64_t state = __atomic_load_n(&input->state, __ATOMIC_ACQUIRE);
    const uint32_t pending = __atomic_exchange_n(&input->pressed, 0, __ATOMIC_ACQ_REL);
    return (Gow3TouchSnapshot) {
        .buttons = (uint32_t)state,
        .pressed = pending,
        .sticks = (uint32_t)(state >> 32),
    };
}

static inline uint32_t gow3_touch_input_buttons(Gow3TouchInput *input) {
    return (uint32_t)__atomic_load_n(&input->state, __ATOMIC_ACQUIRE);
}
