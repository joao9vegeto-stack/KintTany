#!/usr/bin/env python3
"""Backport the sparse mip-view/copy-level fix to the pinned Kakarot NXNative host.

This patch deliberately changes only dm/gfx/nvn/nvn_mtl.m. It does not touch
shader translation, DMSH_CHAIN, guest shader tables, the compiled Metal image,
RomFS, AOC, or game modules.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
SOURCE = Path("dm/gfx/nvn/nvn_mtl.m")

HELPERS = """static unsigned tex_level_shift(const tex_t *t, id<MTLTexture> base) {
    id have = tex_get(t->serial);
    if (![have isKindOfClass:[NvPkg class]]) return 0;
    NvPkg *pk = have;
    return pk->view && pk->view == base ? (unsigned)pk->vbase : 0;
}
// Operations which name NVN mip levels must use the parent: tex_mtl may return
// sparse_view's coarser-level view, whose local level 0 is not NVN level 0.
static id<MTLTexture> tex_mtl_all(const tex_t *t) {
    id<MTLTexture> mt = tex_mtl(t);
    return mt && tex_level_shift(t, mt) ? mt.parentTexture : mt;
}
"""

OLD_LEVEL_START = """        NSUInteger l0 = r.v.set_levels ? r.v.base_level : 0, nl = r.v.set_levels && r.v.nlevels ? r.v.nlevels : base.mipmapLevelCount - l0;
        if (l0 >= base.mipmapLevelCount) { RED_ONCE(109, "texture view id %d starts at mip %lu beyond %lu levels", tid, (unsigned long)l0, (unsigned long)base.mipmapLevelCount); return nil; }
"""
NEW_LEVEL_START = """        NSUInteger lb = tex_level_shift(&rp->t, base), n = base.mipmapLevelCount + lb;
        NSUInteger l0 = r.v.set_levels ? r.v.base_level : 0;
        if (l0 >= n) { RED_ONCE(109, "texture view id %d starts at mip %lu beyond %lu levels", tid, (unsigned long)l0, (unsigned long)n); return nil; }
        NSUInteger nl = r.v.set_levels && r.v.nlevels ? r.v.nlevels : n - l0;
"""
OLD_LEVEL_CLAMP = "        if (nl > base.mipmapLevelCount - l0) nl = base.mipmapLevelCount - l0;\n"
NEW_LEVEL_CLAMP = """        if (nl > n - l0) nl = n - l0;
        // Levels finer than the first mapped one sample from that first resident level.
        if (l0 < lb) { NSUInteger end = l0 + nl; l0 = lb; nl = end > lb ? end - lb : 1; }
        l0 -= lb;
"""

def fail(message: str) -> "NoReturn":
    raise SystemExit(f"[KaKaRoTiOS] Sparse texture backport refused: {message}")

def replace_once(source: str, old: str, new: str, label: str) -> tuple[str, bool]:
    old_n, new_n = source.count(old), source.count(new)
    if old_n == 1 and new_n == 0:
        return source.replace(old, new, 1), True
    if old_n == 0 and new_n == 1:
        return source, False
    fail(f"{label}: expected exactly one original anchor (found {old_n}) or one patched anchor (found {new_n}).")
    raise AssertionError("unreachable")

def replace_in_function(source: str, signature: str, old: str, new: str, label: str) -> tuple[str, bool]:
    start = source.find(signature)
    if start < 0:
        fail(f"{label}: function signature not found: {signature}")
    end = source.find("\n}\n", start)
    if end < 0:
        fail(f"{label}: could not find the function boundary.")
    body = source[start:end]
    updated, changed = replace_once(body, old, new, label)
    return (source[:start] + updated + source[end:], changed)

def patch_source(original: str) -> tuple[str, bool]:
    helper_marker = "static unsigned tex_level_shift(const tex_t *t, id<MTLTexture> base)"
    view_marker = "NSUInteger lb = tex_level_shift(&rp->t, base), n = base.mipmapLevelCount + lb;"
    if helper_marker in original:
        required = [
            "static id<MTLTexture> tex_mtl_all(const tex_t *t)",
            view_marker,
            "id<MTLTexture> t = tex_mtl_all(c->tex);",
            "id<MTLTexture> s = tex_mtl_all(c->src);",
            "id<MTLTexture> d = tex_mtl_all(c->dst);",
        ]
        missing = [item for item in required if item not in original]
        if missing:
            fail("partial prior patch detected; missing markers: " + ", ".join(missing))
        return original, False

    source = original
    anchor = "static id<MTLTexture> tex_by_id(int tid) {"
    source, changed_helper = replace_once(source, anchor, HELPERS + anchor, "insert sparse mip helpers")
    source, changed_level = replace_once(source, OLD_LEVEL_START, NEW_LEVEL_START, "NVN mip-level indexing")
    source, changed_clamp = replace_once(source, OLD_LEVEL_CLAMP, NEW_LEVEL_CLAMP, "sparse mip range clamp")

    source, c_t2b = replace_in_function(
        source, "static void copy_t2b(", "id<MTLTexture> t = tex_mtl(c->tex);",
        "id<MTLTexture> t = tex_mtl_all(c->tex);", "texture-to-buffer copy base texture")
    source, c_b2t = replace_in_function(
        source, "static void copy_b2t(", "id<MTLTexture> t = tex_mtl(c->tex);",
        "id<MTLTexture> t = tex_mtl_all(c->tex);", "buffer-to-texture copy base texture")
    source, c_t2t_src = replace_in_function(
        source, "static void copy_t2t(", "id<MTLTexture> s = tex_mtl(c->src);",
        "id<MTLTexture> s = tex_mtl_all(c->src);", "texture-copy source base texture")
    source, c_t2t_dst = replace_in_function(
        source, "static void copy_t2t(", "id<MTLTexture> d = tex_mtl(c->dst);",
        "id<MTLTexture> d = tex_mtl_all(c->dst);", "texture-copy destination base texture")
    source, c_clear = replace_in_function(
        source, "static void clear_tex(", "id<MTLTexture> t = tex_mtl(c->tex);",
        "id<MTLTexture> t = tex_mtl_all(c->tex);", "texture-clear base texture")

    flags = [changed_helper, changed_level, changed_clamp, c_t2b, c_b2t, c_t2t_src, c_t2t_dst, c_clear]
    if not any(flags):
        fail("no source changes were made.")
    if not all(flags):
        fail("only part of the expected source anchors were changed.")
    for marker in (
        "static unsigned tex_level_shift(const tex_t *t, id<MTLTexture> base)",
        "static id<MTLTexture> tex_mtl_all(const tex_t *t)",
        view_marker,
        "id<MTLTexture> t = tex_mtl_all(c->tex);",
        "id<MTLTexture> s = tex_mtl_all(c->src);",
        "id<MTLTexture> d = tex_mtl_all(c->dst);",
    ):
        if marker not in source:
            fail(f"post-patch verification failed: {marker}")
    return source, True

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true",
                        help="validate all source anchors without writing")
    args = parser.parse_args()

    engine = args.engine_root.resolve()
    pin_file = engine.parent / ".upstream-ref"
    if not pin_file.is_file() or pin_file.read_text(encoding="utf-8").strip() != ENGINE_PIN:
        fail(f"engine pin must be exactly {ENGINE_PIN}.")
    source_file = engine / SOURCE
    if not source_file.is_file():
        fail(f"pinned source file is missing: {source_file}")
    original = source_file.read_text(encoding="utf-8")
    patched, changed = patch_source(original)
    if args.check_only:
        print("[KaKaRoTiOS] Sparse mip-view/copy patch anchors: OK; no files written.")
        return 0
    if changed:
        tmp = source_file.with_suffix(source_file.suffix + ".kakarot-tmp")
        tmp.write_text(patched, encoding="utf-8")
        os.replace(tmp, source_file)
        print("[KaKaRoTiOS] Patched nvn_mtl.m: sparse mip views now count from NVN level 0; copy/clear paths resolve the parent texture.")
    else:
        print("[KaKaRoTiOS] Sparse mip-view/copy patch already applied; source unchanged.")
    print("[KaKaRoTiOS] Host-only patch complete. Guest shaders, DMSH_CHAIN and cached Metal image were not modified.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
