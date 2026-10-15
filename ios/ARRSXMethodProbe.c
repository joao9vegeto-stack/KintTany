/* Guest-like register-file GPU diagnostic, using PINNED upstream RSX engine.
 * NOT PS3 game FIFO or video; no real title code/files are included.
 * Run this only AFTER iPhone RSX Metal backend_init succeeded.
 */
#include <stdint.h>
#include <string.h>
#include "rsx_commands.h"
#include "rsx_draw_engine.h"
#include "rsx_metal_backend.h"
extern int rsx_metal_backend_debug_fixed_probe_stage(void);
int ar_probe_rsx_fixed_stage(void){return rsx_metal_backend_debug_fixed_probe_stage();}
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
    rsx_draw_engine_method(NV4097_SET_COLOR_MASK,0x01010101u);
    rsx_draw_engine_method(NV4097_SET_CULL_FACE_ENABLE,0u);
    rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,0u);
    rsx_draw_engine_method(NV4097_SET_BLEND_ENABLE,0u);
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

/* M4.6 — RSX vertex-DMA probe from bounds-checked, big-endian guest memory.
 * This path differs fundamentally from INLINE_ARRAY: vertices are sourced
 * through the genuine NV4097_SET_VERTEX_DATA_ARRAY_OFFSET DMA mechanism.
 * All values are test-only. No executable or protected title data involved.
 */
extern uint8_t *vm_base;
extern uint32_t ppu_vm_size;
enum { AR_DMA_VERTEX_OFFSET = 0x00200000u, AR_DMA_VERTEX_BYTES = 48u };
static const uint8_t *ar_probe_guest_reader(void *opaque, uint32_t location,
                                            uint32_t offset, uint32_t bytes) {
    (void)opaque;
    if (location != RSX_LOCATION_MAIN && location != RSX_LOCATION_LOCAL) return NULL;
    if (!vm_base || !bytes || (uint64_t)offset + bytes > ppu_vm_size) return NULL;
    return vm_base + offset;
}
static void ar_write_be_float(uint8_t *dest, float number) {
    uint32_t w=f32_word(number);
    dest[0]=(uint8_t)(w>>24); dest[1]=(uint8_t)(w>>16);
    dest[2]=(uint8_t)(w>>8); dest[3]=(uint8_t)w;
}
int ar_probe_rsx_dma_triangle(uint32_t *background, uint32_t *sample) {
    const uint32_t bg=0xff18283du;
    if(background) *background=bg;
    if(sample) *sample=0;
    if(!rsx_draw_engine_enabled()) return -21;
    if(!vm_base || ppu_vm_size < AR_DMA_VERTEX_OFFSET+AR_DMA_VERTEX_BYTES)
        return -22;

    /* Three vertices in main guest memory, IEEE754 float32 in PS3 BE.
     * Write exact words to exercise the real vertex fetch/conversion path. */
    const float xyz[3][4]={{-0.88f,-0.85f,0.f,1.f},
                            { 0.88f,-0.85f,0.f,1.f},
                            { 0.00f, 0.85f,0.f,1.f}};
    uint8_t *dest=vm_base+AR_DMA_VERTEX_OFFSET;
    for(unsigned v=0;v<3;v++)
        for(unsigned c=0;c<4;c++)
            ar_write_be_float(dest+v*16u+c*4u,xyz[v][c]);

    rsx_draw_engine_set_guest_memory(ar_probe_guest_reader,NULL);
    rsx_draw_engine_method(NV4097_SET_CONTEXT_DMA_COLOR_A,
                           CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_HORIZONTAL,AR_WIDTH<<16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_VERTICAL,AR_HEIGHT<<16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_FORMAT,0x5u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_PITCH_A,AR_WIDTH*4u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_AOFFSET,AR_GUEST_RT_OFFSET);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_TARGET,CELL_GCM_SURFACE_TARGET_0);
    rsx_draw_engine_method(NV4097_SET_COLOR_CLEAR_VALUE,bg);
    rsx_draw_engine_method(NV4097_CLEAR_SURFACE,0xf0u);

    rsx_draw_engine_method(NV4097_SET_COLOR_MASK,0x01010101u);
    rsx_draw_engine_method(NV4097_SET_CULL_FACE_ENABLE,0u);
    rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,0u);
    rsx_draw_engine_method(NV4097_SET_BLEND_ENABLE,0u);
    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_FORMAT,
                           2u|(4u<<4)|(16u<<8));
    /* The RSX DMA high bit means MAIN memory. Unlike the inline probe,
     * this forces the vertex fetch planner through eng_guest_ptr. */
    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_OFFSET,
                           0x80000000u|AR_DMA_VERTEX_OFFSET);
    const float color[4]={0.96f,0.30f,0.82f,1.f}; /* magenta */
    for(unsigned c=0;c<4;c++)
        rsx_draw_engine_method(0x1c30u+c*4u,f32_word(color[c]));
    rsx_draw_engine_method(NV4097_SET_BEGIN_END,RSX_PRIMITIVE_TRIANGLES);
    rsx_draw_engine_method(NV4097_DRAW_ARRAYS,(3u-1u)<<24);
    rsx_draw_engine_method(NV4097_SET_BEGIN_END,0u);

    rsx_draw_engine_set_display_buffer(0,RSX_LOCATION_LOCAL,
          AR_GUEST_RT_OFFSET,AR_WIDTH*4u,AR_WIDTH,AR_HEIGHT);
    rsx_draw_engine_method(0xe944u,0u);
    rsx_draw_engine_flush();
    const uint32_t pixel=rsx_draw_engine_readback_center();
    rsx_draw_engine_set_guest_memory(NULL,NULL);
    if(sample) *sample=pixel;
    if(pixel==bg) return -23;
    const unsigned r=(pixel>>16)&255u, g=(pixel>>8)&255u,b=pixel&255u;
    if((pixel>>24)<240u || r<180u || g>140u || b<145u) return -24;
    return 0;
}
