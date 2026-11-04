// SPDX-License-Identifier: GPL-3.0-or-later
#include <assert.h>
#include <stdint.h>
#include "runtime_touch_input.h"

int main(void) {
    Gow3TouchInput input;
    gow3_touch_input_init(&input);

    /* A complete tap between guest polls must still be visible exactly once. */
    gow3_touch_input_publish(&input, UINT32_C(0x4000), GOW3_TOUCH_CENTERED_STICKS);
    gow3_touch_input_publish(&input, 0, GOW3_TOUCH_CENTERED_STICKS);
    Gow3TouchSnapshot sample = gow3_touch_input_read(&input);
    assert(sample.buttons == 0);
    assert(sample.pressed == UINT32_C(0x4000));
    assert(sample.sticks == GOW3_TOUCH_CENTERED_STICKS);
    sample = gow3_touch_input_read(&input);
    assert(sample.buttons == 0);
    assert(sample.pressed == 0);

    /* Held buttons remain level-triggered; a second button gets its own edge. */
    gow3_touch_input_publish(&input, UINT32_C(0x4000), GOW3_TOUCH_CENTERED_STICKS);
    sample = gow3_touch_input_read(&input);
    assert(sample.buttons == UINT32_C(0x4000));
    assert(sample.pressed == UINT32_C(0x4000));
    gow3_touch_input_publish(&input, UINT32_C(0x6000), GOW3_TOUCH_CENTERED_STICKS);
    sample = gow3_touch_input_read(&input);
    assert(sample.buttons == UINT32_C(0x6000));
    assert(sample.pressed == UINT32_C(0x2000));
    gow3_touch_input_publish(&input, 0, GOW3_TOUCH_CENTERED_STICKS);
    sample = gow3_touch_input_read(&input);
    assert(sample.buttons == 0);
    assert(sample.pressed == 0);

    /* Stick axes and button bits are published in one coherent snapshot. */
    const uint32_t sticks = UINT32_C(0x80ff007f);
    gow3_touch_input_publish(&input, UINT32_C(0x8000), sticks);
    sample = gow3_touch_input_read(&input);
    assert(sample.buttons == UINT32_C(0x8000));
    assert(sample.pressed == UINT32_C(0x8000));
    assert(sample.sticks == sticks);

    return 0;
}
