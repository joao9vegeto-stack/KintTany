#!/usr/bin/env python3
"""Surgical native HookLink X1/X3 backports onto verified 1.8.5 nxnative.

Crucially this never updates dmsh_chain.lock, dmsh_chain.h or game shaders.
Sources: original dsi-hub/nxnative commits 2ce8521f3cd7, c03d45bd64d2
and c9aaed502b3d. On an unmatched engine this FAILS CLOSED.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

PIN="cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
GAME="0400486024DEC000"
CHAIN="f8965bffbdf51d78,d17eefaff4f0bc23,a335c1db6270c355>aad7ea7e5c02f41d|b106afba1a18faa9|fa3033d05c0a41d6|04135bb812a0d66e|8df148d58b7cbe8e|d99fbeeb53d38847"

def replace(path, old, new, tag, details):
    text=path.read_text(encoding="utf-8")
    count=text.count(old)
    if count!=1:raise RuntimeError(f"unsafe backport {tag}: {path}: expected one exact anchor, found {count}")
    updated=text.replace(old,new)
    if updated==text:raise RuntimeError("no-op backport: "+tag)
    path.write_text(updated,encoding="utf-8")
    details.append({"source":str(path),"change":tag,"before_sha256":hashlib.sha256(text.encode()).hexdigest(),
                    "after_sha256":hashlib.sha256(updated.encode()).hexdigest()})

def apply(engine):
    actual=subprocess.check_output(["git","-C",str(engine),"rev-parse","HEAD"],text=True).strip()
    if actual!=PIN:raise RuntimeError("refuse non-pinned engine: "+actual)
    lock=engine/"dm/gfx/tools/dmsh_chain.lock"
    locked=hashlib.sha256(lock.read_bytes()).hexdigest()
    details=[]
    profile=engine/"dm/games"/GAME/"game.tsv"
    replace(profile,"mem_reserve\t0x420000000\nmem_alias\t0x200000000",
                    "mem_reserve\t0x620000000\nmem_alias\t0x400000000",
                    "X2 16-GiB alias virtual address space for long sessions and Master Sword",details)
    lines=profile.read_text()
    chainline=next((x for x in lines.splitlines() if x.startswith("upscaler_chain\t")),None)
    if not chainline:raise RuntimeError("missing old upscaler_chain in verified game profile")
    replace(profile,chainline,"upscaler_chain\t"+CHAIN,
            "X3 complete NDSR chain including dynamic-resolution final variant",details)

    gamepy=engine/"dm/games/game.py"
    before="ups = upscaler_keys(g)   # the game's own upscaler shaders, which DM_UPSCALER=metalfx (the launcher's Game's upscaler) replaces with MetalFX's spatial scaler (nvn_mtl.m up_mfx_encode)"
    after=before+"\n    upc = g.get('upscaler_chain', '')\n    if upc and not re.fullmatch(r'[0-9a-f]{16}(,[0-9a-f]{16})*>[0-9a-f]{16}(\\|[0-9a-f]{16})*', upc): sys.exit(f'{g.id}: invalid upscaler chain: {upc}')"
    replace(gamepy,before,after,"X3 validate chain metadata for native host profile header",details)
    before='f\'#define DM_GAME_UPSCALER_KEYS {q(",".join(ups))}\', f\'#define DM_GAME_UPSCALER_N {len(ups)}\','
    after='f\'#define DM_GAME_UPSCALER_KEYS {q(",".join(ups))}\', f\'#define DM_GAME_UPSCALER_CHAIN "{upc}"\', f\'#define DM_GAME_UPSCALER_N {len(ups)}\','
    replace(gamepy,before,after,"X3 pass chain to native host without touching shader translation ABI",details)

    metal=engine/"dm/gfx/nvn/nvn_mtl.m"
    replace(metal,"enum { POOL_SPARES = 16 };",
                 "enum { POOL_SPARES = 64 };   // HookLink X1: texture-table reuse, less CPU work per frame (2ce8521f3cd7)",
                 "X1 64 reusable GPU texture tables, ~11% less per-object CPU work in upstream benchmark",details)
    old="static int up_mfx_wanted(NvShader *cs); static int up_mfx_encode(NvShader *cs);   // a game's upscaler through MetalFX (see up_mfx_encode)"
    replacement="""static int up_mfx_wanted(NvShader *cs); static int up_mfx_encode(NvShader *cs);
static int up_mfx_named(NvShader *cs); static int up_mfx_on(void);
// HookLink X3 (c9aaed502b3d): bypass the whole NDSR network, not just
// its final upscale pass. Keep the first pass's colour input for MetalFX.
static int g_up_chain_in, g_up_chain_refused;
static int up_chain_role(NvShader *cs) {
    const char *c = DM_GAME_UPSCALER_CHAIN;
    if (!*c || !cs->key[0]) return 0;
    const char *last = strchr(c, '>');
    if (!last) return 0;
    for (const char *p = last + 1; strlen(p) >= 16; p += 17) {
        if (!strncmp(p, cs->key, 16)) return 3;
        if (p[16] != '|') break;
    }
    for (const char *p = c; p < last; p += 17)
        if (!strncmp(p, cs->key, 16)) return p == c ? 2 : 1;
    return 0;
}"""
    replace(metal,old,replacement,"X3 NDSR chain identification and fail-safe state",details)
    old='if (ndve_engine_dispatch(cs, dp)) return;   // nn::ndve\'s movie network as the host\'s kernels (DM_NDVE_ENGINE=1)'
    new=old+"""
    // HookLink X3: MetalFX replaces NDSR feature/network/blend/last
    // dispatches. If it refuses the final pass, use the game's chain on
    // following frames rather than keep skipping it.
    {
        int role = up_mfx_on() && !g_up_chain_refused ? up_chain_role(cs) : 0;
        if (role == 2) {
            g_up_chain_in = 0;
            for (int i=0; i<cs->rf.nb; i++) if (cs->rf.b[i].kind==NVN_RB_TEX) {
                g_up_chain_in=(int)(tex_slot_h(S.tex[5], S.img[5], cs->rf.b[i].reg)&0xfffff);
                break;
            }
        }
        if ((role==1 || role==2) && g_up_chain_in) return;
        if (role==3) {
            if (g_up_chain_in && !dp->ind && up_mfx_encode(cs)) {
                g_up_chain_in=0; return;
            }
            if (g_up_chain_in) {
                g_up_chain_refused=1;
                MLOG("[RED] X3 NDSR chain: MetalFX refused last stage %s; disable chain bypass",cs->key);
            }
            g_up_chain_in=0;
        }
        if (!role && g_up_chain_in && up_mfx_named(cs)) {
            if (!dp->ind && up_mfx_encode(cs)) { g_up_chain_in=0; return; }
            g_up_chain_refused=1; g_up_chain_in=0;
            MLOG("[RED] X3 NDSR chain: unknown last stage %s; disable bypass",cs->key);
        }
    }"""
    replace(metal,old,new,"X3 bypass NDSR intermediate GPU dispatches with safe fallbacks",details)
    old='int tin = (int)(tex_slot_h(S.tex[5], S.img[5], cs->rf.b[ti].reg) & 0xfffff), tout = cs->rf.b[oi].reg < 32 ? (int)(S.img[5][cs->rf.b[oi].reg] & 0xfffff) : 0;'
    new=old+'\n    if (g_up_chain_in) tin = g_up_chain_in;  // X3: first NDSR pass colour, intermediate network skipped'
    replace(metal,old,new,"X3 MetalFX reads original scene colour, not network output",details)
    old='int srgb = cs->up_color == UP_COLOR_SRGB;'
    new='int srgb = cs->up_color == UP_COLOR_SRGB && !g_up_chain_in;  // X3: scene input is linear HDR'
    replace(metal,old,new,"X3 linear colour handling when bypassing NDSR network",details)
    afterlock=hashlib.sha256(lock.read_bytes()).hexdigest()
    if locked!=afterlock:raise RuntimeError("shader compiler lock changed; refuse")
    return {"engine_pin":PIN,"title_id":GAME,
            "original_shaders_preserved":True,
            "shader_chain_lock_sha256":locked,
            "upstream_native_commits":["2ce8521f3cd7","c03d45bd64d2","c9aaed502b3d"],
            "changes":details}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--engine",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()
    report=apply(a.engine.resolve())
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+"\n")
    print("HOOKLINK2IOS_NATIVE_BACKPORT_OK",len(report["changes"]),"source modifications; old shader chain untouched",flush=True)
if __name__=="__main__":main()
