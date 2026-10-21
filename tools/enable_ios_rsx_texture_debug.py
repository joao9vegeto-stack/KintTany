#!/usr/bin/env python3
"""Temporary CI overlay: sample the texture actually bound by RSX DRAW.

Only touches disposable pinned upstream rsx_metal_backend.m during CI.
No game binaries. Does NOT claim the fixed PS3 guest fragment shader samples
this unit; the synthetic GPU COMPUTE sampler samples that exact resource,
after a register-file draw caused the engine to upload and bind it.
"""
import argparse
from pathlib import Path

def patch(source:str)->str:
    bind="static void eng_bind_textures(void* user, const u32* textures,"
    draw="static void eng_encode_draw(id<MTLRenderCommandEncoder> enc, const EngRecord* r,"
    if source.count(bind)!=1 or source.count(draw)!=1:
        raise ValueError("Pinned upstream RSX texture/draw hooks changed")
    helper=r'''/* M4.9 diagnostics. Record texture0 only after a REAL engine DRAW reaches
 * Metal command encoding; a mere texture-state change cannot pass this test. */
static u32 ar_probe_draw_tex0;
void rsx_metal_backend_debug_reset_texture_probe(void) {
    ar_probe_draw_tex0=0;
}
int rsx_metal_backend_debug_sample_texture0(u32 out[4]) {
    if(out) memset(out,0,sizeof(u32)*4);
    if(!out || !s_dev || !ar_probe_draw_tex0) return -1;
    id<MTLTexture> tex=eng_obj(ar_probe_draw_tex0);
    if(!tex || tex.width!=8 || tex.height!=8) return -2;
    NSString* src=@"#include <metal_stdlib>\n"
      "using namespace metal;\n"
      "kernel void rsx_probe_sample(texture2d<float,access::sample> t [[texture(0)]],\n"
      "device uint* dst [[buffer(0)]], uint idx [[thread_position_in_grid]]) {\n"
      " if(idx>=4)return;\n"
      " constexpr sampler s(filter::nearest,address::clamp_to_edge);\n"
      " float2 uv=float2((idx%2==0?2.5:6.5)/8.0,(idx<2?2.5:6.5)/8.0);\n"
      " float4 c=t.sample(s,uv);\n"
      " uint4 k=uint4(round(clamp(c,0.0,1.0)*255.0));\n"
      " dst[idx]=(k.a<<24)|(k.r<<16)|(k.g<<8)|k.b;\n"
      "}\n";
    NSError *err=nil;
    id<MTLLibrary> lib=[s_dev newLibraryWithSource:src options:nil error:&err];
    if(!lib){fprintf(stderr,"[M4.9] MSL: %s\n",[[err localizedDescription] UTF8String]);return -3;}
    id<MTLFunction> fn=[lib newFunctionWithName:@"rsx_probe_sample"];
    if(!fn)return -4;
    id<MTLComputePipelineState> pso=[s_dev newComputePipelineStateWithFunction:fn error:&err];
    if(!pso)return -5;
    id<MTLBuffer> buffer=[s_dev newBufferWithLength:4*sizeof(u32)
                               options:MTLResourceStorageModeShared];
    id<MTLCommandQueue> queue=[s_dev newCommandQueue];
    if(!buffer||!queue)return -6;
    id<MTLCommandBuffer> cmd=[queue commandBuffer];
    if(!cmd)return -7;
    id<MTLComputeCommandEncoder> enc=[cmd computeCommandEncoder];
    if(!enc)return -8;
    [enc setComputePipelineState:pso];
    [enc setTexture:tex atIndex:0];
    [enc setBuffer:buffer offset:0 atIndex:0];
    [enc dispatchThreads:MTLSizeMake(4,1,1)
      threadsPerThreadgroup:MTLSizeMake(4,1,1)];
    [enc endEncoding];
    [cmd commit];
    [cmd waitUntilCompleted];
    if(cmd.status!=MTLCommandBufferStatusCompleted){
        fprintf(stderr,"[M4.9] GPU: %s\n",[[cmd.error localizedDescription] UTF8String]);
        return -9;
    }
    memcpy(out,buffer.contents,4*sizeof(u32));
    return 0;
}

'''
    source=source.replace(bind,helper+bind,1)
    begin=source.index(draw)
    snippet=source[begin:]
    # PS3Recomp 39a made a missing guest PSO a sticky engine fault; the older
    # a2c runtime returned without recording it.  Both guards sit at the same
    # point in the real encoder, after the draw record and pipeline resolve.
    guards=(
        "    if (!p->pso) return;",
        "    if (!p->pso) { s_eng_encoding_failed = 1; return; }",
    )
    matches=[guard for guard in guards if snippet.count(guard)==1]
    if len(matches)!=1:
        raise ValueError("Metal draw PSO guard unexpectedly absent or ambiguous")
    anchor=matches[0]
    snippet=snippet.replace(anchor,anchor+'''
    if(r->tex[0]) ar_probe_draw_tex0=r->tex[0];
''',1)
    source=source[:begin]+snippet
    return source

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("upstream",type=Path)
    args=parser.parse_args()
    path=args.upstream/"libs/video/rsx_metal_backend.m"
    path.write_text(patch(path.read_text()))
    print("RSX texture0 draw binding + GPU compute readback probe enabled")
