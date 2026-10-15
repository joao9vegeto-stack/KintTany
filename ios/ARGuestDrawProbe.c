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
extern int ar_probe_m51_shader_state(uint32_t out[4]);
extern void ar_probe_cache_reset(void);
extern uint32_t ar_probe_cache_uploads(void);
extern uint32_t ar_probe_cache_replacements(void);
extern void ar_probe_m53_reset_views(void);
extern uint32_t ar_probe_m53_surface_views(void);
extern void ar_probe_m54_reset_depth_draws(void);
extern uint32_t ar_probe_m54_depth_draws(void);

enum {
    M51_RT_OFFSET = 0x00100000u,
    M51_TEX_OFFSET = 0x00280000u,
    M51_VBO_OFFSET = 0x00290000u,
    M51_EBO_OFFSET = 0x002A0000u,
    M51_FP_OFFSET  = 0x002B0000u,
    M53_RT_B_OFFSET = 0x00600000u,
    M54_Z_OFFSET = 0x00C00000u,
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
    rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,0u);
    rsx_draw_engine_method(NV4097_SET_DEPTH_MASK,0u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_FORMAT,0x5u);
    rsx_draw_engine_method(NV4097_SET_VERTEX_DATA_ARRAY_FORMAT + 8u*4u,0u);
    rsx_draw_engine_set_guest_memory(NULL,NULL);
}

/* M5.3 uses exactly the same guest NV4097 VP/FP draw for both passes.
 * sample_surface=0: texture from guest MAIN at M51_TEX_OFFSET.
 * sample_surface=1: texture from a PREVIOUS RSX LOCAL render surface
 * at M51_RT_OFFSET, not from host-injected pixels or a compute shader.
 * All legacy M5.1/M5.2 calls use the same defaults as before. */
static int m51_guest_textured_quad_palette_ex(unsigned swizzled,
                            unsigned palette, unsigned sample_surface,
                            uint32_t destination,
                            float vertex_z, unsigned depth_mode,
                            uint32_t pixels[4], unsigned *encoded,
                            unsigned *guest_draws, uint32_t shader_state[4]) {
    if (!pixels || !encoded || !guest_draws || !shader_state) return -101;
    memset(shader_state,0,4u*sizeof(uint32_t));
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
    if (!sample_surface) for (unsigned y=0;y<M51_TEX_H;y++) for(unsigned x=0;x<M51_TEX_W;x++) {
        unsigned color=((x>=4u) + (y>=4u ? 2u : 0u) + palette) & 3u;
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
        m51_be32(vbo+i*32u+c*4u,m51_word(c==2u?vertex_z:v[i][c]));
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
        rsx_draw_engine_method(NV4097_SET_TRANSFORM_PROGRAM+(i&3u)*4u,word);
    }
    rsx_draw_engine_method(NV4097_SET_TRANSFORM_PROGRAM_START,0u);
    rsx_draw_engine_method(NV4097_SET_SHADER_PROGRAM,M51_FP_OFFSET|2u);
    rsx_draw_engine_method(NV4097_SET_SHADER_CONTROL,0x40u); /* FP32 export */

    rsx_draw_engine_method(NV4097_SET_TEXTURE_OFFSET,
                            sample_surface ? M51_RT_OFFSET : M51_TEX_OFFSET);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_FORMAT,
        (1u<<16) | ((sample_surface ? 0xA5u : (swizzled?0x85u:0xA5u))<<8)
                  | (2u<<4) | (sample_surface ? 1u : 2u));
    rsx_draw_engine_method(NV4097_SET_TEXTURE_ADDRESS,0x00030303u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_CONTROL0,0x80000000u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_CONTROL1,0x0000AAE4u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_FILTER,0x01010000u);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_IMAGE_RECT,
        sample_surface ? (M51_WIDTH<<16)|M51_HEIGHT : (M51_TEX_W<<16)|M51_TEX_H);
    rsx_draw_engine_method(NV4097_SET_TEXTURE_CONTROL3,
        sample_surface ? M51_WIDTH*4u : M51_TEX_W*4u);

    rsx_draw_engine_method(NV4097_SET_CONTEXT_DMA_COLOR_A,
                           CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_HORIZONTAL,M51_WIDTH<<16);
    rsx_draw_engine_method(NV4097_SET_SURFACE_CLIP_VERTICAL,M51_HEIGHT<<16);
    /* Depth Z24S8 is explicitly configured ONLY in the M5.4 depth probe.
     * Older GPU paths keep their previously proven colour-only state. */
    rsx_draw_engine_method(NV4097_SET_SURFACE_FORMAT,
                           depth_mode ? (0x5u | (2u<<5)) : 0x5u);
    if(depth_mode) {
        rsx_draw_engine_method(NV4097_SET_CONTEXT_DMA_ZETA,
             CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER);
        rsx_draw_engine_method(NV4097_SET_SURFACE_ZETA_OFFSET,M54_Z_OFFSET);
        rsx_draw_engine_method(NV4097_SET_SURFACE_PITCH_Z,M51_WIDTH*4u);
        rsx_draw_engine_method(NV4097_SET_ZSTENCIL_CLEAR_VALUE,0xffffff00u);
        rsx_draw_engine_method(NV4097_SET_DEPTH_FUNC,0x0201u); /* LESS */
        rsx_draw_engine_method(NV4097_SET_DEPTH_MASK,1u);
        rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,1u);
    }
    rsx_draw_engine_method(NV4097_SET_SURFACE_PITCH_A,M51_WIDTH*4u);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_AOFFSET,destination);
    rsx_draw_engine_method(NV4097_SET_SURFACE_COLOR_TARGET,CELL_GCM_SURFACE_TARGET_0);
    rsx_draw_engine_method(NV4097_SET_COLOR_CLEAR_VALUE,0xff101820u);
    /* phase 1 clears both depth and colour; phases 2/3 MUST load
     * them unchanged or occlusion could not be tested. */
    if (depth_mode!=2u)
        rsx_draw_engine_method(NV4097_CLEAR_SURFACE,
                               depth_mode ? 0xf1u : 0xf0u);
    rsx_draw_engine_method(NV4097_SET_COLOR_MASK,0x01010101u);
    rsx_draw_engine_method(NV4097_SET_CULL_FACE_ENABLE,0u);
    /* M5.4.1: Do NOT silently disable depth after configuring Z24S8!
     * Legacy M5.1-M5.3 still issue the exact old depth-disable command,
     * whereas M5.4 must keep LESS+write enabled across all 3 draws.
     * The prior unconditional write caused both LINEAR and SWIZZLED
     * on-device phase-2 failure -424 and depth DRAW counter 0. */
    if (!depth_mode)
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
        destination,M51_WIDTH*4u,M51_WIDTH,M51_HEIGHT);
    rsx_draw_engine_method(0xE944u,0u);
    rsx_draw_engine_flush();

    ar_probe_m51_shader_state(shader_state);
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

/* Compatibility wrapper: every tested legacy path remains guest MAIN
 * texture sampling into the original render target. */
static int m51_guest_textured_quad_palette(unsigned swizzled, unsigned palette,
                                    uint32_t pixels[4], unsigned *encoded,
                                    unsigned *guest_draws, uint32_t shader_state[4]) {
    return m51_guest_textured_quad_palette_ex(swizzled,palette,0u,M51_RT_OFFSET,
                                              0.0f,0u,pixels,encoded,guest_draws,shader_state);
}

/* The M5.1 externally visible probe remains behavior-identical. M5.2 calls
 * the same real NV4097 route with rotated guest memory pixels each frame. */
int ar_probe_m51_guest_textured_quad(unsigned swizzled,
                                    uint32_t pixels[4], unsigned *encoded,
                                    unsigned *guest_draws, uint32_t shader_state[4]) {
    return m51_guest_textured_quad_palette(swizzled,0u,pixels,encoded,
                                          guest_draws,shader_state);
}

/* M5.2: one guest texture address, identical NV4097 registers, three
 * DIFFERENT guest-memory contents, three real translated TEX0 GPU draws.
 * The backend's existing per-frame content-hash logic MUST replace the Metal
 * resource; it is not sufficient to pass an independent host compute sample.
 * For each frame, check ORDERED GPU quadrants against rotated guest colors.
 */
int ar_probe_m52_guest_texture_mutation(unsigned swizzled,
                          uint32_t pixels[4], unsigned *failed_phase,
                          unsigned *uploads, unsigned *replacements,
                          unsigned *guest_total, unsigned *metal_total) {
    if (!pixels || !failed_phase || !uploads || !replacements ||
        !guest_total || !metal_total) return -201;
    *failed_phase=*uploads=*replacements=*guest_total=*metal_total=0;
    memset(pixels,0,4u*sizeof(*pixels));
    ar_probe_cache_reset();
    for (unsigned phase=0;phase<3u;phase++) {
        unsigned encoded=0, guest=0;
        uint32_t shader[4]={0};
        *failed_phase=phase+1u;
        const int rc=m51_guest_textured_quad_palette(swizzled,phase,pixels,
                                                     &encoded,&guest,shader);
        *guest_total+=guest;
        *metal_total+=encoded;
        if (rc) {
            *uploads=ar_probe_cache_uploads();
            *replacements=ar_probe_cache_replacements();
            return rc;
        }
        if (guest!=1u || encoded!=1u) return -210-(int)phase;
        /* GPU readback is in top-left, top-right, bottom-left, bottom-right
         * order. A rotated palette must be correct at each position, not
         * merely contain the same four colors in some order. */
        for (unsigned q=0;q<4u;q++)
            if (pixels[q]!=m51_colors[(q+phase)&3u])
                return -220-(int)(phase*4u+q);
    }
    *uploads=ar_probe_cache_uploads();
    *replacements=ar_probe_cache_replacements();
    if (*replacements<2u) return -240;
    if (*uploads<2u) return -241;
    if (*guest_total!=3u || *metal_total!=3u) return -242;
    *failed_phase=0u;
    return 0;
}
 
/* M5.3: real RSX-to-RSX multipass. Pass A samples PS3 guest texture in
 * MAIN and draws into LOCAL colour surface A. Pass B samples that SAME GPU
 * render target A as TEX0 (through eng_surface_view) and writes to
 * separate LOCAL colour surface B. Both are genuine translated VP/FP TEX0
 * NV4097 indexed draws, not blits or host compute shaders. */
int ar_probe_m53_guest_multipass(unsigned swizzled, uint32_t pixels[4],
       unsigned *phase, unsigned *guest_total, unsigned *metal_total,
       unsigned *surface_views, unsigned *new_uploads) {
    if (!pixels || !phase || !guest_total || !metal_total ||
        !surface_views || !new_uploads) return -301;
    *phase=*guest_total=*metal_total=*surface_views=*new_uploads=0u;
    memset(pixels,0,4u*sizeof(*pixels));
    uint32_t shader[4]={0};
    unsigned encoded=0,guest=0;
    *phase=1u;
    int rc=m51_guest_textured_quad_palette_ex(swizzled,0u,0u,M51_RT_OFFSET,
                                              0.0f,0u,pixels,&encoded,&guest,shader);
    *guest_total+=guest; *metal_total+=encoded;
    if(rc) return rc;
    if(guest!=1u || encoded!=1u) return -302;
    for(unsigned q=0;q<4u;q++)
        if(pixels[q]!=m51_colors[q]) return -310-(int)q;

    /* Record ONLY the second pass's native surface-view bindings.
     * A fallback decode of guest memory would produce zero views, FAIL. */
    ar_probe_m53_reset_views();
    ar_probe_cache_reset();
    memset(shader,0,sizeof(shader));
    encoded=guest=0u;
    *phase=2u;
    rc=m51_guest_textured_quad_palette_ex(swizzled,0u,1u,M53_RT_B_OFFSET,
                                          0.0f,0u,pixels,&encoded,&guest,shader);
    *guest_total+=guest; *metal_total+=encoded;
    *surface_views=ar_probe_m53_surface_views();
    *new_uploads=ar_probe_cache_uploads();
    if(rc) return rc;
    if(guest!=1u || encoded!=1u) return -303;
    if(*surface_views<1u) return -304;
    /* Sampling from the existing GPU surface must not upload its guest
     * address into a new standalone texture in this second pass. */
    if(*new_uploads!=0u) return -305;
    for(unsigned q=0;q<4u;q++)
        if(pixels[q]!=m51_colors[q]) return -320-(int)q;
    if(*guest_total!=2u || *metal_total!=2u) return -330;
    *phase=0u;
    return 0;
}

/* M5.4: genuine NV40 guest VP/FP TEX0 + persistent Z24S8 on Metal.
 * Pass 1 writes the base quad at z=0.45 with LESS and depth writes ON.
 * Pass 2 (z=0.85, palette +1) must fail the depth test: original pixels.
 * Pass 3 (z=0.10, palette +2) must pass and overwrite colour/depth.
 * Each pass reads GPU pixels from the real RSX target; two different colour
 * palettes make "depth disabled" and "depth cleared each time" fail closed. */
int ar_probe_m54_guest_depth_occlusion(unsigned swizzled,
           uint32_t pixels[4], unsigned *phase,
           unsigned *guest_total,unsigned *metal_total,unsigned *depth_draws) {
    if(!pixels||!phase||!guest_total||!metal_total||!depth_draws) return -401;
    *phase=*guest_total=*metal_total=*depth_draws=0u;
    memset(pixels,0,4u*sizeof(*pixels));
    const float depths[3]={0.45f,0.85f,0.10f};
    const unsigned palettes[3]={0u,1u,2u};
    const unsigned expected[3]={0u,0u,2u};
    ar_probe_m54_reset_depth_draws();
    for(unsigned i=0;i<3u;i++) {
        unsigned guest=0u,encoded=0u;
        uint32_t shader[4]={0u,0u,0u,0u};
        *phase=i+1u;
        const int rc=m51_guest_textured_quad_palette_ex(
            swizzled,palettes[i],0u,M51_RT_OFFSET,depths[i],
            i==0u ? 1u : 2u,pixels,&encoded,&guest,shader);
        *guest_total+=guest; *metal_total+=encoded;
        if(rc) {
            *depth_draws=ar_probe_m54_depth_draws();
            return rc;
        }
        if(guest!=1u||encoded!=1u) return -410-(int)i;
        for(unsigned q=0;q<4u;q++)
            if(pixels[q]!=m51_colors[(q+expected[i])&3u])
                return -420-(int)(i*4u+q);
    }
    *depth_draws=ar_probe_m54_depth_draws();
    if(*depth_draws!=3u) return -440;
    if(*guest_total!=3u||*metal_total!=3u) return -441;
    *phase=0u;
    return 0;
}
