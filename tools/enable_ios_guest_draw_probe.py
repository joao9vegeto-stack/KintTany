#!/usr/bin/env python3
"""M5.1 only: CI-only fail-closed instrumentation for real guest RSX draws.

Do not alter the renderer's shader selection or insert a synthetic fragment
program. Observe a translated TEX0 pipeline after Metal command encoding,
and read pixels directly from the guest RSX render target after a GPU fence.
"""
import argparse
from pathlib import Path

def patch_engine(s):
    needle = "u32 rsx_draw_engine_readback_center(void)"
    if s.count(needle) != 1:
        raise ValueError("pinned RSX readback hook changed")
    helper = r'''/* M5.1: four separate points in the REAL last-presented RSX target.
 * No compute shader, host-generated colour, or texture substitution. */
int ar_probe_m51_readback_quad(u32 out[4]) {
    if (!out) return -1;
    memset(out, 0, 4u * sizeof(u32));
    if (!g.ready || !g.be || !g.be->readback) return -2;
    const u32 slot = g.last_present_surface;
    if (slot >= g.n_surfaces) return -3;
    const eng_surface* s = &g.surfaces[slot];
    if (!s->handle || s->fmt != RSX_BE_FMT_R8G8B8A8 ||
        s->w < 8u || s->h < 8u) return -4;
    for (u32 i = 0; i < 4; i++) {
        const u32 x = (s->w * ((i & 1u) ? 3u : 1u)) / 4u;
        const u32 y = (s->h * ((i & 2u) ? 3u : 1u)) / 4u;
        u8 pixel[4] = {0, 0, 0, 0};
        g.be->readback(g.be->user, s->handle, x, y, 1u, 1u, pixel, 4u);
        out[i] = ((u32)pixel[3] << 24) | ((u32)pixel[0] << 16)
               | ((u32)pixel[1] << 8) | (u32)pixel[2];
    }
    return 0;
}

'''
    residency = r'''/* Synthetic M5.1.3 introspection. This measures the real
 * active dispatcher VP and guest FP bytes before cleanup, not a simulation. */
int ar_probe_m51_shader_state(u32 out[4]) {
    if (!out) return -1;
    memset(out, 0, 4u*sizeof(u32));
    if (!g.ready) return -2;
    const u8 *vp = NULL, *fp = NULL;
    u32 vi = 0, fs = 0;
    out[0] = (u32)eng_guest_programs(&vp, &vi, &fp, &fs);
    out[1] = vi;
    out[2] = fs;
    out[3] = rsx_dsp_reg(&g.rsx, 0x08E4u);
    return 0;
}

'''
    native_views = r'''/* M5.3: instrument ACTUAL GPU surface views, never a separate
 * texture upload. Count only a successful view handle for a sampled
 * previous RSX render target, not guest decode or compute fallback. */
static u32 ar_m53_surface_view_count;
void ar_probe_m53_reset_views(void) { ar_m53_surface_view_count=0; }
u32 ar_probe_m53_surface_views(void) { return ar_m53_surface_view_count; }

'''
    view_anchor = "            textures[u] = view ? view : g.surfaces[sampled].handle;"
    if s.count(view_anchor) != 1:
        raise ValueError("pinned RTT GPU surface view selection changed")
    s=s.replace(view_anchor,
        "            if (view) ar_m53_surface_view_count++;\n" + view_anchor,1)
    early_anchor = "static u32 sink_bind_textures("
    if s.count(early_anchor) != 1:
        raise ValueError("pinned native RTT sampling entry changed")
    s=s.replace(early_anchor, native_views + early_anchor,1)
    return s.replace(needle, helper + residency + needle, 1)

def patch_metal(s):
    a = "    MTLWinding  winding;\n} EngPipeline;"
    if s.count(a) != 1:
        raise ValueError("pinned Metal PSO layout changed")
    s = s.replace(a, "    MTLWinding  winding;\n    u8 ar_m51_tex0; /* synthetic probe: genuine translated fragment TEX0 */\n} EngPipeline;", 1)
    a = "static u32 s_eng_pipe_count;"
    if s.count(a) != 1:
        raise ValueError("pinned Metal PSO cache changed")
    s = s.replace(a, a + """
static u32 ar_m51_draws_encoded;
void ar_probe_m51_reset_draws(void) { ar_m51_draws_encoded = 0; }
u32 ar_probe_m51_encoded_draws(void) { return ar_m51_draws_encoded; }
""", 1)
    a = "    s_eng_pipe[slot].pso = pso;"
    if s.count(a) != 1:
        raise ValueError("pinned PSO creation changed")
    s = s.replace(a, a + """
    /* Mark only the HLSL generated from the actual fragment microcode.
     * The fixed pipeline can never satisfy this predicate. */
    s_eng_pipe[slot].ar_m51_tex0 =
        strstr(ps_hlsl, "rsx_tex[0].Sample(") != NULL;
""", 1)
    a = "vertexStart:0 vertexCount:r->vertex_count];"
    if s.count(a) != 1:
        raise ValueError("pinned draw encoding changed")
    s = s.replace(a, a + """
    if (p->ar_m51_tex0 && r->tex[0] && eng_obj(r->tex[0]))
        ar_m51_draws_encoded++;
""", 1)
    return s

def apply(upstream):
    a = upstream / "libs/video/rsx_draw_engine.c"
    b = upstream / "libs/video/rsx_metal_backend.m"
    newa = patch_engine(a.read_text())
    newb = patch_metal(b.read_text())
    a.write_text(newa)
    b.write_text(newb)
    print("M5.1: real RSX guest TEX0 draw/quad GPU readback instrumentation enabled")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("upstream", type=Path)
    apply(ap.parse_args().upstream)
