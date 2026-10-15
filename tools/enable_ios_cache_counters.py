#!/usr/bin/env python3
"""Hardware-only counters for the pinned upstream RSX texture cache.

No behavior change to caching: count actual successful backend uploads
and content-hash-induced replacement of Metal texture resources.
"""
import argparse
from pathlib import Path
def patch(s):
    anchor="static u32 eng_texture_upload(u32 location, u32 offset, u32 fmt, u32 w, u32 h,"
    helper="""/* Synthetic M4.10 instrumentation, not a cache implementation change. */
static u32 ar_cache_uploads, ar_cache_replacements;
void ar_probe_cache_reset(void) {ar_cache_uploads=0; ar_cache_replacements=0;}
u32 ar_probe_cache_uploads(void) {return ar_cache_uploads;}
u32 ar_probe_cache_replacements(void) {return ar_cache_replacements;}

"""
    if s.count(anchor)!=1:raise ValueError("Upstream uploader anchor changed")
    s=s.replace(anchor,helper+anchor,1)
    anchor="    if (!handle) return 0;\n\n    for (u32 f = 0;"
    if s.count(anchor)!=1:raise ValueError("Upstream texture-create guard changed")
    s=s.replace(anchor,"    if (!handle) return 0;\n    ar_cache_uploads++;\n\n    for (u32 f = 0;",1)
    anchor="                if (fresh) {\n                    g.be->texture_release"
    if s.count(anchor)!=1:raise ValueError("Upstream texture hash/replacement guard changed")
    s=s.replace(anchor,"                if (fresh) {\n                    ar_cache_replacements++;\n                    g.be->texture_release",1)
    return s
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("upstream",type=Path)
    a=p.parse_args()
    path=a.upstream/"libs/video/rsx_draw_engine.c"
    path.write_text(patch(path.read_text()))
    print("M4.10 RSX content hash cache counters installed")
