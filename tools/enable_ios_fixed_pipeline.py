#!/usr/bin/env python3
"""Only patch pinned temporary iOS checkout. No false guest shader support."""
import argparse,json
from pathlib import Path
def edit(source,metal):
    marker='static u32 eng_pipeline_create(void* user, const char* vs_hlsl,'
    if source.count(marker)!=1:raise ValueError('upstream pipeline signature shifted')
    helper=r'''/* Hardware fixed shader pair for the engine's BUILT-IN HLSL only.
 * The iPhone excludes glslang/spirv-cross: do not fake game shaders. */
static int ar_fixed_stage;
static id<MTLLibrary> ar_fixed_lib;
int rsx_metal_backend_debug_fixed_probe_stage(void) {return ar_fixed_stage;}
static id<MTLFunction> ar_fixed_msl(int is_vertex) {
 if(!s_dev)return nil;
 if(!ar_fixed_lib) {
   NSError *error=nil;
   NSString *src=[NSString stringWithUTF8String:__MSL_SOURCE__];
   ar_fixed_lib=[s_dev newLibraryWithSource:src options:nil error:&error];
   if(!ar_fixed_lib) {
     fprintf(stderr,"[RSX metal fixed] %s\n",
       [[error localizedDescription] UTF8String]);
     return nil;
   }
 }
 if(ar_fixed_stage<1)ar_fixed_stage=1;
 return [ar_fixed_lib newFunctionWithName:
          (is_vertex?@"ar_fixed_vertex":@"ar_fixed_fragment")];
}

'''.replace('__MSL_SOURCE__',json.dumps(metal))
    source=source.replace(marker,helper+marker,1)
    old='if (!s_dev || !s_guest_shaders || !vertex_stride) return 0;'
    if source.count(old)!=1:raise ValueError('upstream shader gate shifted')
    source=source.replace(old,'''if(!s_dev||!vertex_stride)return 0;
    /* Exact upstream built-in fallback, never an arbitrary guest shader. */
    const int fixed_pair=
      strstr(vs_hlsl,"Out.col0 = input.a3;") &&
      strstr(vs_hlsl,"vp_posscale") &&
      strstr(ps_hlsl,"return input.col0;");
    if(!s_guest_shaders&&!fixed_pair)return 0;''',1)
    old='id<MTLFunction> vs = eng_function(vs_hlsl, RSX_SHADER_STAGE_VERTEX, "vp");'
    if source.count(old)!=1:raise ValueError('vertex function anchor changed')
    source=source.replace(old,'''id<MTLFunction> vs=fixed_pair ? ar_fixed_msl(1)
      : eng_function(vs_hlsl,RSX_SHADER_STAGE_VERTEX,"vp");''',1)
    old='id<MTLFunction> fs = eng_function(ps_hlsl, RSX_SHADER_STAGE_FRAGMENT, "fp");'
    if source.count(old)!=1:raise ValueError('fragment function anchor changed')
    source=source.replace(old,'''id<MTLFunction> fs=fixed_pair ? ar_fixed_msl(0)
      : eng_function(ps_hlsl,RSX_SHADER_STAGE_FRAGMENT,"fp");''',1)
    old='    MTLDepthStencilDescriptor* dd = [MTLDepthStencilDescriptor new];'
    if source.count(old)!=2:
        # Present both guest backend and draw engine; insert only inside
        # eng_pipeline_create rather than accidentally patching global path.
        first=source.index(marker)
        at=source.find(old,first)
        if at<0:raise ValueError('pipeline state insertion missing')
        source=source[:at]+'''    if(fixed_pair&&ar_fixed_stage<2)ar_fixed_stage=2;
'''+source[at:]
    else:
        first=source.index(marker)
        at=source.find(old,first)
        source=source[:at]+'''    if(fixed_pair&&ar_fixed_stage<2)ar_fixed_stage=2;
'''+source[at:]
    old='    r->index_count  = indices ? index_count : 0;'
    if source.count(old)!=1:raise ValueError('draw staging changed')
    source=source.replace(old,old+'''
    if(ar_fixed_stage==2)ar_fixed_stage=3;''',1)
    return source
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('upstream',type=Path)
    p.add_argument('metal',type=Path)
    a=p.parse_args()
    path=a.upstream/'libs/video/rsx_metal_backend.m'
    path.write_text(edit(path.read_text(),a.metal.read_text()))
    print('Enabled Metal built-in fixed shader pair only; unknown HLSL remains unsupported')
