/* Guest-like register-file GPU diagnostic, using PINNED upstream RSX engine.
 * NOT PS3 game FIFO or video; no real title code/files are included.
 * Run this only AFTER iPhone RSX Metal backend_init succeeded.
 */
#include <stdint.h>
#include <string.h>
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

/* M4.4: native NV4097 inline-array GEOMETRY smoke test.
 * Genuine RSX method path, not a Metal clear. Uses the guest-engine's
 * documented fixed-program fallback; NOT translated game shaders.
 * The 3 vertices form a center-covering green triangle on a dark clear.
 */
static uint32_t f32_word(float f) {
    uint32_t w=0; memcpy(&w,&f,sizeof w); return w;
}
int ar_probe_rsx_triangle(uint32_t *background, uint32_t *sample) {
    const uint32_t bg=0xff142034u;
    if(background) *background=bg;
    if(sample) *sample=0;
    if(!rsx_draw_engine_enabled()) return -11;

    rsx_draw_engine_method(NV4097_SET_CONTEXT_DMA_COLOR_A,
                           CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_HORIZONTAL, AR_WIDTH << 16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_VERTICAL, AR_HEIGHT << 16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_FORMAT, 0x5u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_PITCH_A, AR_WIDTH*4u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_AOFFSET, AR_GUEST_RT_OFFSET);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_TARGET,
                           CELL_GCM_SURFACE_TARGET_0);
    rsx_draw_engine_method(NV4097_SET_COLOR_CLEAR_VALUE,bg);
    rsx_draw_engine_method(NV4097_CLEAR_SURFACE,0xf0u);
    if(rsx_metal_backend_debug_color()!=bg) return -12;

    /* ATTR0 = float4; inline values are uploaded by the guest method
     * exactly as in the pinned rsx_draw_engine's synthetic test fixture.
     * ATTR3 is a constant (disabled array) that the fixed fragment
     * shader returns as COLOR0, so no program decompiler is involved. */
    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_FORMAT, 
                           2u | (4u<<4) | (16u<<8));
    const float green[4]={0.10f,0.96f,0.28f,1.0f};
    for(unsigned lane=0;lane<4;lane++)
        rsx_draw_engine_method(0x1c30u+lane*4u,f32_word(green[lane]));
    const float points[3][4]={
        {-0.90f,-0.90f,0.0f,1.0f},
        { 0.90f,-0.90f,0.0f,1.0f},
        { 0.00f, 0.90f,0.0f,1.0f}
    };
    rsx_draw_engine_method(NV4097_SET_BEGIN_END,RSX_PRIMITIVE_TRIANGLES);
    for(unsigned v=0;v<3;v++)
        for(unsigned lane=0;lane<4;lane++)
            rsx_draw_engine_method(0x1818u,f32_word(points[v][lane]));
    rsx_draw_engine_method(NV4097_SET_BEGIN_END,0u);

    rsx_draw_engine_set_display_buffer(0,RSX_LOCATION_LOCAL,
        AR_GUEST_RT_OFFSET, AR_WIDTH*4u, AR_WIDTH, AR_HEIGHT);
    rsx_draw_engine_method(0xe944u,0u);
    rsx_draw_engine_flush();
    const uint32_t pixel=rsx_draw_engine_readback_center();
    if(sample) *sample=pixel;
    /* Reject the all-clear frame. The center must be green dominant.
     * A pipeline/shader/upload failure must be visible in the UI as FAIL.
     * Keep the raw ARGB visible rather than hiding channel corruption. */
    if(pixel==bg) return -13;
    const unsigned red=(pixel>>16)&255u, g=(pixel>>8)&255u,
                   blue=pixel&255u,alpha=pixel>>24;
    if(alpha<240u || g<195u || red>110u || blue>150u) return -14;
    return 0;
}
