/* M5.1: genuine NV4097 guest VP/FP TEX0 -> RSX draw-engine -> Metal
 * rasterisation. Verifies four pixels from the actual guest render target.
 * Synthetic PS3 input data ONLY: no Ascension ELF/assets, no fake shaders.
 * Must be run on the main thread after the Metal backend/VM is ready.
 */
#include <stdint.h>
#include <string.h>
#include "rsx_commands.h"
#include "rsx_draw_engine.h"
#include "rsx_test_programs.h"
#include "rsx_texture_layout.h"

extern uint8_t *vm_base;
extern uint32_t ppu_vm_size;
extern void ar_probe_m51_reset_draws(void);
extern uint32_t ar_probe_m51_encoded_draws(void);
extern int ar_probe_m51_readback_quad(uint32_t out[4]);

enum {
    M51_RT_OFFSET = 0x00100000u,
    M51_TEX_OFFSET = 0x00280000u,
    M51_VBO_OFFSET = 0x00290000u,
    M51_EBO_OFFSET = 0x002A0000u,
    M51_FP_OFFSET  = 0x002B0000u,
    M51_WIDTH = 960u, M51_HEIGHT = 540u,
    M51_TEX_W = 8u, M51_TEX_H = 8u
};
static const uint32_t m51_colors[4] = {
    0xffff0000u, 0xff00ff00u, 0xff0000ffu, 0xffffff00u
};
static uint32_t m51_word(float f) {
    uint32_t v=0; memcpy(&v, &f, sizeof(v)); return v;
}
static void m51_be32(uint8_t *p, uint32_t v) {
    p[0]=(uint8_t)(v>>24); p[1]=(uint8_t)(v>>16);
    p[2]=(uint8_t)(v>>8); p[3]=(uint8_t)v;
}
static const uint8_t *m51_guest_read(void *unused, uint32_t loc,
                                     uint32_t off, uint32_t bytes) {
    (void)unused;
    if (loc!=RSX_LOCATION_LOCAL && loc!=RSX_LOCATION_MAIN) return NULL;
    if (!vm_base || !bytes || (uint64_t)off + bytes > ppu_vm_size) return NULL;
    return vm_base + off;
}
static void m51_cleanup(void) {
    /* Crucial: never leave the guest pair active for M4.3-M4.10 probes. */
    rsx_draw_engine_method(NV4097_SET_SHADER_PROGRAM,0u);
    rsx_draw_engine_method(NV4097_SET_SHADER_CONTROL,0u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_CONTROL0,0u);
    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_FORMAT + 8u*4u,0u);
    rsx_draw_engine_set_guest_memory(NULL,NULL);
}

int ar_probe_m51_guest_textured_quad(unsigned swizzled,
                                    uint32_t pixels[4], unsigned *encoded,
                                    unsigned *guest_draws) {
    if (!pixels || !encoded || !guest_draws) return -101;
    memset(pixels,0,4u*sizeof(*pixels));
    *encoded=0; *guest_draws=0;
    if (!rsx_draw_engine_enabled()) return -102;
    if (!vm_base || (uint64_t)M51_FP_OFFSET+16u>ppu_vm_size ||
        (uint64_t)M51_EBO_OFFSET+12u>ppu_vm_size ||
        (uint64_t)M51_VBO_OFFSET+128u>ppu_vm_size) return -103;

    /* The same 8x8 A,R,G,B quadrants used by the proven M4.9 cache path;
     * either linear pitch or PS3 Morton swizzle, decoded by the engine. */
    const uint8_t colors[4][4]={
        {255,0,0,255}, {0,255,0,255}, {0,0,255,255}, {255,255,0,255}
    };
    uint8_t *texture=vm_base+M51_TEX_OFFSET;
    for (unsigned y=0;y<M51_TEX_H;y++) for(unsigned x=0;x<M51_TEX_W;x++) {
        unsigned color=(x>=4u) + (y>=4u ? 2u : 0u);
        unsigned i=swizzled ? rsx_swizzle_offset(x,y,3u,3u) : y*M51_TEX_W+x;
        uint8_t *d=texture+i*4u;
        d[0]=colors[color][3]; d[1]=colors[color][0];
        d[2]=colors[color][1]; d[3]=colors[color][2];
    }

    /* Guest BE float4 position and float4 texcoord, interleaved stride=32.
     * The RSX input analyser maps ATTR0 / ATTR8 into compact Metal slots. */
    static const float v[4][8] = {
        {-1.f, 1.f,0.f,1.f,  0.f,0.f,0.f,1.f},
        { 1.f, 1.f,0.f,1.f,  1.f,0.f,0.f,1.f},
        { 1.f,-1.f,0.f,1.f,  1.f,1.f,0.f,1.f},
        {-1.f,-1.f,0.f,1.f,  0.f,1.f,0.f,1.f}
    };
    uint8_t *vbo=vm_base+M51_VBO_OFFSET;
    for(unsigned i=0;i<4;i++) for(unsigned c=0;c<8;c++)
        m51_be32(vbo+i*32u+c*4u,m51_word(v[i][c]));
    const unsigned ix[6]={0,1,2,0,2,3};
    uint8_t *ebo=vm_base+M51_EBO_OFFSET;
    for(unsigned i=0;i<6;i++) {
        ebo[i*2u]=(uint8_t)(ix[i]>>8);
        ebo[i*2u+1]=(uint8_t)ix[i];
    }

    /* Actual 2-instruction NV40 VP: MOV o0 (HPOS), ATTR0; MOV o7 (TC0),
     * ATTR8. Actual 1-instruction NV40 FP: TEX r0, TC0, texture unit 0. */
    uint8_t vp[32],fp[16];
    rsx_test_vp_mov_out(vp,0,RSX_TEST_VP_SWZ_IDENT,0,0);
    rsx_test_vp_mov_out(vp+16,8,RSX_TEST_VP_SWZ_IDENT,7,1);
    rsx_test_fp_tex_r0_tc0(fp,0);
    memcpy(vm_base+M51_FP_OFFSET,fp,sizeof(fp));

    rsx_draw_engine_set_guest_memory(m51_guest_read,NULL);
    ar_probe_m51_reset_draws();

    rsx_draw_engine_method(NV4097_SET_TRANSFORM_PROGRAM_LOAD,0u);
    for(unsigned i=0;i<8;i++) {
        uint32_t word=(uint32_t)vp[i*4u] |
          ((uint32_t)vp[i*4u+1]<<8) | ((uint32_t)vp[i*4u+2]<<16) |
          ((uint32_t)vp[i*4u+3]<<24);
        rsx_draw_engine_method(NV4097_SET_TRANSFORM_PROGRAM,word);
    }
    rsx_draw_engine_method(NV4097_SET_TRANSFORM_PROGRAM_START,0u);
    rsx_draw_engine_method(NV4097_SET_SHADER_PROGRAM,M51_FP_OFFSET|1u);
    rsx_draw_engine_method(NV4097_SET_SHADER_CONTROL,0x40u); /* FP32 export */

    rsx_draw_engine_method(NV4097_SET_TEXTURE_OFFSET,M51_TEX_OFFSET);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_FORMAT,
        (1u<<16) | ((swizzled?0x85u:0xA5u)<<8) | (2u<<4) | 2u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_ADDRESS,0x00030303u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_CONTROL0,0x80000000u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_CONTROL1,0x0000AAE4u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_FILTER,0x01010000u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_IMAGE_RECT,
                           (M51_TEX_W<<16)|M51_TEX_H);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_CONTROL3,M51_TEX_W*4u);

    rsx_draw_engine_method(NV4097_SET_CONTEXT_DMA_COLOR_A,
                           CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_HORIZONTAL,M51_WIDTH<<16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_VERTICAL,M51_HEIGHT<<16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_FORMAT,0x5u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_PITCH_A,M51_WIDTH*4u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_AOFFSET,M51_RT_OFFSET);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_TARGET,CELL_GCM_SURFACE_TARGET_0);
    rsx_draw_engine_method(NV4097_SET_COLOR_CLEAR_VALUE,0xff101820u);
    rsx_draw_engine_method(NV4097_CLEAR_SURFACE,0xf0u);
    rsx_draw_engine_method(NV4097_SET_COLOR_MASK,0x01010101u);
    rsx_draw_engine_method(NV4097_SET_CULL_FACE_ENABLE,0u);
    rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,0u);
    rsx_draw_engine_method(NV4097_SET_BLEND_ENABLE,0u);

    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_FORMAT,
                           2u | (4u<<4) | (32u<<8));
    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_OFFSET,
                           0x80000000u | M51_VBO_OFFSET);
    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_FORMAT+8u*4u,
                           2u | (4u<<4) | (32u<<8));
    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_OFFSET+8u*4u,
                           0x80000000u | (M51_VBO_OFFSET+16u));
    rsx_draw_engine_method(NV4097_SET_INDEX_ARRAY_ADDRESS,M51_EBO_OFFSET);
    rsx_draw_engine_method(NV4097_SET_INDEX_ARRAY_DMA,1u | 0x10u); /* MAIN u16 */
    rsx_draw_engine_method(NV4097_SET_BEGIN_END,RSX_PRIMITIVE_TRIANGLES);
    rsx_draw_engine_method(NV4097_DRAW_INDEX_ARRAY,(6u-1u)<<24);
    rsx_draw_engine_method(NV4097_SET_BEGIN_END,0u);

    rsx_draw_engine_set_display_buffer(0,RSX_LOCATION_LOCAL,
        M51_RT_OFFSET,M51_WIDTH*4u,M51_WIDTH,M51_HEIGHT);
    rsx_draw_engine_method(0xE944u,0u);
    rsx_draw_engine_flush();

    *guest_draws=rsx_draw_engine_guest_draws();
    *encoded=ar_probe_m51_encoded_draws();
    int read_rc=ar_probe_m51_readback_quad(pixels);
    m51_cleanup();
    if(!*guest_draws)return -104;  /* fixed fallback is not evidence */
    if(!*encoded)return -105;      /* must bind compiled FP TEX0 at GPU draw */
    if(read_rc)return -110+read_rc;
    /* Require the actual guest fragment program to sample four DISTINCT
     * expected texels, not return a constant/fixed shader or background.
     * Compare as a colour set so raster Y orientation is visible separately. */
    unsigned found=0;
    for(unsigned i=0;i<4;i++) {
        unsigned index=4;
        for(unsigned c=0;c<4;c++) if(pixels[i]==m51_colors[c])index=c;
        if(index>=4 || (found&(1u<<index)))return -120-(int)i;
        found |= 1u<<index;
    }
    return found==15u ? 0 : -125;
}
