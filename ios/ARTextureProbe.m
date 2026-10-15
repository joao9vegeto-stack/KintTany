/* M4.8 — PS3 RSX A8R8G8B8 texture decoder -> actual iPhone Metal texture
 * -> fragment shader sampling -> GPU readback and onscreen presentation.
 *
 * This is a strictly isolated TEXTURE-FORMAT diagnostic. It does not claim
 * that real game fragment microcode or NV4097 texture binding is supported.
 */
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#include <stdint.h>
#include <string.h>
#include "rsx_texture_layout.h"
extern uint8_t *vm_base;
extern uint32_t ppu_vm_size;

enum { AR_TEX_W=8, AR_TEX_H=8, AR_TEX_OFFSET=0x00260000u };
static const uint8_t ar_rgba_quadrants[4][4] = {
    {255,0,0,255}, {0,255,0,255}, {0,0,255,255}, {255,255,0,255}
};

static uint32_t ar_pack_argb(const uint8_t *rgba) {
    return ((uint32_t)rgba[3]<<24)|((uint32_t)rgba[0]<<16)|
           ((uint32_t)rgba[1]<<8)|rgba[2];
}

static id<MTLRenderPipelineState> ar_pipeline(id<MTLDevice> dev,
        id<MTLFunction> vertex, id<MTLFunction> fragment,
        MTLPixelFormat format) {
    MTLRenderPipelineDescriptor *desc=[MTLRenderPipelineDescriptor new];
    desc.vertexFunction=vertex;
    desc.fragmentFunction=fragment;
    desc.colorAttachments[0].pixelFormat=format;
    NSError *error=nil;
    id<MTLRenderPipelineState> p=[dev newRenderPipelineStateWithDescriptor:desc
                                                                   error:&error];
    if(!p)NSLog(@"[M4.8] Metal pipeline %@: %@",@(format),error);
    return p;
}

static int ar_draw_texture(id<MTLCommandQueue> queue,
                           id<MTLRenderPipelineState> pipeline,
                           id<MTLTexture> output, id<MTLTexture> sampled,
                           id<CAMetalDrawable> drawable) {
    if(!queue || !pipeline || !output || !sampled)return -1;
    MTLRenderPassDescriptor *pass=[MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture=output;
    pass.colorAttachments[0].loadAction=MTLLoadActionClear;
    pass.colorAttachments[0].storeAction=MTLStoreActionStore;
    pass.colorAttachments[0].clearColor=MTLClearColorMake(0.05,0.05,0.06,1.0);
    id<MTLCommandBuffer> cmd=[queue commandBuffer];
    if(!cmd)return -2;
    id<MTLRenderCommandEncoder> enc=[cmd renderCommandEncoderWithDescriptor:pass];
    if(!enc)return -3;
    [enc setRenderPipelineState:pipeline];
    [enc setFragmentTexture:sampled atIndex:0];
    [enc drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:6];
    [enc endEncoding];
    if(drawable)[cmd presentDrawable:drawable];
    [cmd commit];
    [cmd waitUntilCompleted];
    if(cmd.status!=MTLCommandBufferStatusCompleted){
        NSLog(@"[M4.8] GPU sampling command failed: %@",cmd.error);
        return -4;
    }
    return 0;
}

/* Uses the installed layer/device of the proven RSX Metal backend.
 * Result 0 requires BOTH a correct decoded PS3 texture and correct colors
 * after GPU fragment sampling. Success is not inferred from app startup. */
#ifdef __cplusplus
extern "C"
#endif
int ar_probe_rsx_texture(void *raw_layer,unsigned swizzled,uint32_t out_pixels[4]) {
    if(out_pixels)memset(out_pixels,0,sizeof(uint32_t)*4);
    if(![NSThread isMainThread])return -41;
    if(!vm_base || (uint64_t)AR_TEX_OFFSET+AR_TEX_W*AR_TEX_H*4u>ppu_vm_size)
        return -42;

    CAMetalLayer *layer=(__bridge CAMetalLayer *)raw_layer;
    id<MTLDevice> dev=layer.device;
    if(!dev)return -43;

    /* PS3 guest A8R8G8B8: source bytes are A,R,G,B (NOT RGBA).
     * Alternate linear and Morton-swizzled layouts between test gestures. */
    uint8_t *guest=vm_base+AR_TEX_OFFSET;
    for(unsigned y=0;y<AR_TEX_H;y++)
        for(unsigned x=0;x<AR_TEX_W;x++){
            unsigned q=(x>=4u)+(y>=4u?2u:0u);
            const uint8_t *c=ar_rgba_quadrants[q];
            unsigned pos=swizzled ? rsx_swizzle_offset(x,y,3u,3u)
                                  : (y*AR_TEX_W+x);
            uint8_t *p=guest+4u*pos;
            p[0]=c[3];p[1]=c[0];p[2]=c[1];p[3]=c[2];
        }
    rsx_tex_layout layout;
    rsx_texture_layout_pitched(swizzled?0x85u:0xA5u,AR_TEX_W,AR_TEX_H,
                              swizzled?0u:AR_TEX_W*4u,&layout);
    if(layout.swizzled!=(int)(swizzled!=0u) ||
       layout.dst_row_bytes!=AR_TEX_W*4u || layout.compressed)
        return -44;

    uint8_t decoded[AR_TEX_W*AR_TEX_H*4u]={0};
    rsx_texture_decode(decoded,AR_TEX_W*4u,guest,AR_TEX_W,AR_TEX_H,&layout,0);
    for(unsigned q=0;q<4;q++){
        unsigned x=(q&1u)?6u:2u,y=(q&2u)?6u:2u;
        if(memcmp(decoded+(y*AR_TEX_W+x)*4u,ar_rgba_quadrants[q],4u))
            return -45;
    }

    MTLTextureDescriptor *td=[MTLTextureDescriptor
        texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm
        width:AR_TEX_W height:AR_TEX_H mipmapped:NO];
    td.usage=MTLTextureUsageShaderRead;
    id<MTLTexture> source=[dev newTextureWithDescriptor:td];
    if(!source)return -46;
    [source replaceRegion:MTLRegionMake2D(0,0,AR_TEX_W,AR_TEX_H)
             mipmapLevel:0 withBytes:decoded bytesPerRow:AR_TEX_W*4u];

    NSString *code=
        @"#include <metal_stdlib>\n"
         "using namespace metal;\n"
         "struct V {float4 pos [[position]];float2 uv;};\n"
         "vertex V ar_tex_vert(uint id [[vertex_id]]){\n"
         " const float2 p[6]={float2(-1,-1),float2(1,-1),float2(-1,1),\n"
         "                    float2(1,-1),float2(1,1),float2(-1,1)};\n"
         " V o;o.pos=float4(p[id],0,1);\n"
         " o.uv=float2(p[id].x*0.5+0.5,0.5-p[id].y*0.5);return o;\n"
         "}\n"
         "fragment float4 ar_tex_frag(V v [[stage_in]],\n"
         " texture2d<float> tex [[texture(0)]]){\n"
         " constexpr sampler s(filter::nearest,address::clamp_to_edge);\n"
         " return tex.sample(s,v.uv);\n"
         "}\n";
    NSError *error=nil;
    id<MTLLibrary> library=[dev newLibraryWithSource:code options:nil error:&error];
    if(!library){NSLog(@"[M4.8] MSL translation %@",error);return -47;}
    id<MTLFunction> vs=[library newFunctionWithName:@"ar_tex_vert"];
    id<MTLFunction> fs=[library newFunctionWithName:@"ar_tex_frag"];
    if(!vs || !fs)return -48;
    id<MTLRenderPipelineState> offPSO=ar_pipeline(dev,vs,fs,MTLPixelFormatRGBA8Unorm);
    id<MTLRenderPipelineState> onPSO=ar_pipeline(dev,vs,fs,layer.pixelFormat);
    if(!offPSO||!onPSO)return -49;
    id<MTLCommandQueue> queue=[dev newCommandQueue];
    if(!queue)return -50;

    /* Read back FOUR independent pixels produced by fragment sampling.
     * 64x64 is 8x magnification of the 8x8 guest source. */
    MTLTextureDescriptor *outDesc=[MTLTextureDescriptor
        texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm
        width:64 height:64 mipmapped:NO];
    outDesc.usage=MTLTextureUsageRenderTarget;
    outDesc.storageMode=MTLStorageModeShared;
    id<MTLTexture> offscreen=[dev newTextureWithDescriptor:outDesc];
    if(!offscreen)return -51;
    if(ar_draw_texture(queue,offPSO,offscreen,source,nil)!=0)return -52;

    const unsigned samples[4][2]={{16,16},{48,16},{16,48},{48,48}};
    unsigned seen=0;
    for(unsigned i=0;i<4;i++){
        uint8_t rgba[4]={0};
        [offscreen getBytes:rgba bytesPerRow:4u
                fromRegion:MTLRegionMake2D(samples[i][0],samples[i][1],1,1)
               mipmapLevel:0];
        uint32_t argb=ar_pack_argb(rgba);
        if(out_pixels)out_pixels[i]=argb;
        unsigned idx=4;
        for(unsigned k=0;k<4;k++)
            if(argb==ar_pack_argb(ar_rgba_quadrants[k]))idx=k;
        if(idx>=4 || (seen&(1u<<idx)))return -53;
        seen|=1u<<idx;
    }
    if(seen!=0x0fu)return -54;

    /* Separate presentation to the ACTUAL CAMetalLayer. A successful
     * offscreen sample with failed onscreen display reports failure. */
    id<CAMetalDrawable> drawable=[layer nextDrawable];
    if(!drawable)return -55;
    if(ar_draw_texture(queue,onPSO,drawable.texture,source,drawable)!=0)
        return -56;
    return 0;
}
