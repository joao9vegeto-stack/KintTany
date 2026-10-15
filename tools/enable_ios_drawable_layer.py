#!/usr/bin/env python3
"""Add a device CAMetalLayer bridge to pinned PS3Recomp Metal backend.

Only patches temporary CI upstream checkout. Does not create game assets or
change macOS rendering behavior. Requires the M3.9 offscreen overlay first.
"""
import argparse
from pathlib import Path

def patch_metal(s: str) -> str:
    anchor='static CAMetalLayer*       s_layer;      /* windowed only   */'
    if s.count(anchor)!=1:
        raise ValueError('Metal layer slot changed in upstream')
    s=s.replace(anchor, anchor+'\nstatic CAMetalLayer*       s_ios_layer;  /* UIKit-provided, before init */',1)
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
            s_layer.drawableSize = CGSizeMake((CGFloat)s_width,
                                              (CGFloat)s_height);
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
    return s

def patch_public_header(s: str) -> str:
    anchor='int  rsx_metal_backend_init(u32 width, u32 height, const char* title);'
    if s.count(anchor)!=1:
        raise ValueError('public Metal header changed')
    return s.replace(anchor,
      '''/* iOS: call from UIKit main thread before backend_init.
 * Supply CAMetalLayer* via opaque pointer. Returns 0 only on iOS.
 * No ownership transfer, keep the view alive while rendering. */
int  rsx_metal_backend_set_ios_layer(void *metal_layer);
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
