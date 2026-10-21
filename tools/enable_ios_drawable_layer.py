#!/usr/bin/env python3
"""Add a device CAMetalLayer bridge to pinned PS3Recomp Metal backend.

Only patches temporary CI upstream checkout. Does not create game assets or
change macOS rendering behavior. Requires the M3.9 offscreen overlay first.
"""
import argparse
from pathlib import Path

def patch_metal(s: str) -> str:
    if "rsx_metal_backend_set_ios_output_scale" in s:
        if "ASCENSION_IOS_DRAWABLE_SCALE_V1" not in s:
            raise ValueError('a partial iOS Metal output-scale patch is present')
        return s
    anchor='static CAMetalLayer*       s_layer;      /* windowed only   */'
    if s.count(anchor)!=1:
        raise ValueError('Metal layer slot changed in upstream')
    s=s.replace(anchor, anchor+'\nstatic CAMetalLayer*       s_ios_layer;  /* UIKit-provided, before init */',1)
    if s.count(anchor+'\nstatic CAMetalLayer*       s_ios_layer;  /* UIKit-provided, before init */') != 1:
        raise ValueError('Metal iOS layer slot was not inserted exactly once')
    scale_anchor='static u32                 s_height = 720;'
    if s.count(scale_anchor)!=1:
        raise ValueError('Metal output dimensions changed')
    s=s.replace(scale_anchor, scale_anchor+'\n#if TARGET_OS_IPHONE\nstatic CGFloat              s_ios_output_scale = 1.0;\n#endif',1)
    depth_anchor='''    MTLTextureDescriptor* td =
        [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTL_DEPTH_FORMAT
                                                           width:s_width
                                                          height:s_height
                                                       mipmapped:NO];'''
    depth_scaled='''#if TARGET_OS_IPHONE
    const NSUInteger depth_width = (NSUInteger)((CGFloat)s_width * s_ios_output_scale);
    const NSUInteger depth_height = (NSUInteger)((CGFloat)s_height * s_ios_output_scale);
#else
    const NSUInteger depth_width = s_width;
    const NSUInteger depth_height = s_height;
#endif
    MTLTextureDescriptor* td =
        [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTL_DEPTH_FORMAT
                                                           width:(depth_width ? depth_width : 1)
                                                          height:(depth_height ? depth_height : 1)
                                                       mipmapped:NO];'''
    if s.count(depth_anchor)!=1:
        raise ValueError('Metal shared depth texture allocation changed')
    s=s.replace(depth_anchor,depth_scaled,1)
    api='int rsx_metal_backend_init(u32 width, u32 height, const char* title)'
    if s.count(api)!=1:
        raise ValueError('Metal init hook changed')
    setter='''/* iPhone drawable presentation: the caller MUST invoke on UIKit's main
 * thread BEFORE rsx_metal_backend_init, and keep the UIView alive. */
int rsx_metal_backend_set_ios_layer(void *opaque_layer)
{
#if TARGET_OS_IPHONE
    if (s_ready || !opaque_layer) return -1;
    s_ios_layer = (__bridge CAMetalLayer*)opaque_layer;
    return s_ios_layer ? 0 : -1;
#else
    (void)opaque_layer;
    return -1;
#endif
}

/* ASCENSION_IOS_DRAWABLE_SCALE_V1. Scale only the Metal presentation
 * drawable. Guest RSX render-target dimensions remain controlled by the game. */
int rsx_metal_backend_set_ios_output_scale(float scale)
{
#if TARGET_OS_IPHONE
    if (s_ready || !(scale >= 0.5f && scale <= 1.0f)) return -1;
    s_ios_output_scale = (CGFloat)scale;
    if (s_layer)
        s_layer.drawableSize = CGSizeMake((CGFloat)s_width * s_ios_output_scale,
                                          (CGFloat)s_height * s_ios_output_scale);
    return 0;
#else
    (void)scale;
    return -1;
#endif
}

'''
    s=s.replace(api,setter+api,1)
    before='''#if TARGET_OS_IPHONE
        s_headless = 1;
        rc = create_offscreen();
#else'''
    after='''#if TARGET_OS_IPHONE
        if (s_ios_layer) {
            /* No offscreen fallback: present to the actual UIKit layer. */
            s_layer = s_ios_layer;
            s_layer.device = s_dev;
            s_layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
            s_layer.framebufferOnly = YES;
            s_layer.drawableSize = CGSizeMake((CGFloat)s_width * s_ios_output_scale,
                                              (CGFloat)s_height * s_ios_output_scale);
            s_headless = 0;
            rc = 0;
        } else {
            s_headless = 1;
            rc = create_offscreen();
        }
#else'''
    if s.count(before)!=1:
        raise ValueError('iOS backend init branch unexpectedly changed')
    s=s.replace(before,after,1)
    render_target='''    s_width = w; s_height = h;
    if (s_layer) s_layer.drawableSize = CGSizeMake((CGFloat)w, (CGFloat)h);'''
    scaled_render_target='''    s_width = w; s_height = h;
#if TARGET_OS_IPHONE
    if (s_layer) s_layer.drawableSize = CGSizeMake((CGFloat)w * s_ios_output_scale,
                                                   (CGFloat)h * s_ios_output_scale);
#else
    if (s_layer) s_layer.drawableSize = CGSizeMake((CGFloat)w, (CGFloat)h);
#endif'''
    if s.count(render_target)!=1:
        raise ValueError('Metal guest render-target resize hook changed')
    s=s.replace(render_target,scaled_render_target,1)
    return s

def patch_public_header(s: str) -> str:
    if "rsx_metal_backend_set_ios_output_scale" in s:
        if "rsx_metal_backend_set_ios_layer" not in s:
            raise ValueError('a partial iOS Metal header patch is present')
        return s
    anchor='int  rsx_metal_backend_init(u32 width, u32 height, const char* title);'
    if s.count(anchor)!=1:
        raise ValueError('public Metal header changed')
    return s.replace(anchor,
      '''/* iOS: call from UIKit main thread before backend_init.
 * Supply CAMetalLayer* via opaque pointer. Returns 0 only on iOS.
 * No ownership transfer, keep the view alive while rendering. */
int  rsx_metal_backend_set_ios_layer(void *metal_layer);
/* iOS: scale the presentation drawable, 0.5 through 1.0. */
int  rsx_metal_backend_set_ios_output_scale(float scale);
'''+anchor,1)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('upstream',type=Path)
    a=ap.parse_args()
    source=a.upstream/'libs/video/rsx_metal_backend.m'
    header=a.upstream/'libs/video/rsx_metal_backend.h'
    new_source=patch_metal(source.read_text())
    new_header=patch_public_header(header.read_text())
    source.write_text(new_source)
    header.write_text(new_header)
    print('Added explicit UIKit CAMetalLayer presentation hook for iOS.')

if __name__=='__main__':
    main()
