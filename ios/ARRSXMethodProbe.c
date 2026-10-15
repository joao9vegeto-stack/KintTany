/* Guest-like register-file GPU diagnostic, using PINNED upstream RSX engine.
 * NOT PS3 game FIFO or video; no real title code/files are included.
 * Run this only AFTER iPhone RSX Metal backend_init succeeded.
 */
#include <stdint.h>
#include "rsx_commands.h"
#include "rsx_draw_engine.h"
#include "rsx_metal_backend.h"
enum { AR_WIDTH = 960u, AR_HEIGHT = 540u, AR_GUEST_RT_OFFSET = 0x100000u };
static const uint32_t ar_clear_colors[] = {
    0xffff5828u, /* orange / red */
    0xfff6bc24u, /* amber */
    0xff38cae8u  /* cyan */
};
int ar_probe_rsx_clear_flip(unsigned cycle, uint32_t *expected, uint32_t *observed) {
    const uint32_t argb=ar_clear_colors[cycle % 3u];
    if(expected) *expected=argb;
    if(observed) *observed=0;
    if(!rsx_draw_engine_enabled()) return -1;

    /* NV4097 register writes (same method decoding as a guest GPU command
     * list), not a direct Metal call. The color surface is deliberately a
     * local RSX target, with no untrusted host pointer dereference. */
    rsx_draw_engine_method(NV4097_SET_CONTEXT_DMA_COLOR_A,
                           CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_HORIZONTAL, AR_WIDTH << 16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_VERTICAL, AR_HEIGHT << 16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_FORMAT, 0x5u); /* A8R8G8B8 */
    rsx_draw_engine_method(NV4097_SET_SURFACE_PITCH_A, AR_WIDTH * 4u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_AOFFSET, AR_GUEST_RT_OFFSET);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_TARGET,
                           CELL_GCM_SURFACE_TARGET_0);
    rsx_draw_engine_method(NV4097_SET_COLOR_CLEAR_VALUE, argb);
    rsx_draw_engine_method(NV4097_CLEAR_SURFACE, 0xF0u);  /* RGBA clear */

    /* A set-value alone is insufficient: the Metal back end updates this
     * latch only when the RSX engine successfully builds a surface and its
     * clear callback fires. */
    if(rsx_metal_backend_debug_color()!=argb) return -2;

    rsx_draw_engine_set_display_buffer(0, RSX_LOCATION_LOCAL,
         AR_GUEST_RT_OFFSET, AR_WIDTH * 4u, AR_WIDTH, AR_HEIGHT);

    /* Send a real driver-queue flip method through the dispatcher, instead
     * of invoking a direct drawing or presentation helper. */
    rsx_draw_engine_method(0xE944u, 0u);
    rsx_draw_engine_flush();  /* GPU fence for readback */
    const uint32_t pixel=rsx_draw_engine_readback_center();
    if(observed) *observed=pixel;
    if(pixel!=argb) return -3;   /* Never claim RSX success on mismatch. */
    return 0;
}
