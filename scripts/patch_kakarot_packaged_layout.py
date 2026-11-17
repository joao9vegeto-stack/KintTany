#!/usr/bin/env python3
"""Backport NVN packaged-texture width alignment into the pinned Kakarot host.

The 8-byte NVNpackagedTextureLayout carries a width-alignment log2 in
layout[1]'s low nibble. The pinned Kakarot engine kept only layout[0], which
made row pitch, mip offsets, and array-layer alignment too small for layouts
with a non-zero width nibble. This is a host/runtime fix: it never changes
guest shaders, DMSH_CHAIN, or the cached Metal shader image.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
FILES = (
    "dm/gfx/nvn/hle_nvn.c",
    "dm/gfx/nvn/nvn_tex.c",
    "dm/gfx/nvn/nvn_tex.h",
    "dm/gfx/nvn/nvn_mtl.m",
    "dm/gfx/tex/nvn_deswizzle.c",
    "dm/gfx/tests/t_tex_layout.c",
    "dm/gfx/tests/t_nvn.c",
)

def fail(message: str) -> "NoReturn":
    raise SystemExit(f"[KaKaRoTiOS] Packaged texture layout backport refused: {message}")

def replace_once(source: str, old: str, new: str, label: str) -> tuple[str, bool]:
    old_n, new_n = source.count(old), source.count(new)
    if old_n == 1 and new_n == 0:
        return source.replace(old, new, 1), True
    if old_n == 0 and new_n == 1:
        return source, False
    fail(f"{label}: expected exactly one original anchor (found {old_n}) or one patched anchor (found {new_n}).")
    raise AssertionError("unreachable")

def patch_hle(source: str) -> tuple[str, bool]:
    changed = False
    source, did = replace_once(
        source,
        "    TB(b)->d.pkg_block_h = l ? l->layout[0] + 1 : 0;",
        "    TB(b)->d.pkg_block_h = l ? (l->layout[0] | ((l->layout[1] & 0xf) << 8)) + 1 : 0;",
        "preserve packaged H/D/W layout nibbles",
    )
    changed |= did
    old_fmt = '        LOG("[nvn] packaged texture %ux%ux%u levels %u format %#x target %d layout bytes %02x%02x%02x%02x%02x%02x%02x%02x → block height log2=%u (from layout byte 0) size %#llx",'
    new_fmt = '        LOG("[nvn] packaged texture %ux%ux%u levels %u format %#x target %d layout bytes %02x%02x%02x%02x%02x%02x%02x%02x → block height log2=%u width alignment log2=%u size %#llx",'
    source, did = replace_once(source, old_fmt, new_fmt, "report packaged width alignment")
    changed |= did
    old_args = "            b->layout[3], b->layout[4], b->layout[5], b->layout[6], b->layout[7], L->tileH, L->size);"
    new_args = "            b->layout[3], b->layout[4], b->layout[5], b->layout[6], b->layout[7], L->tileH, b->layout[1] & 0xf, L->size);"
    source, did = replace_once(source, old_args, new_args, "print packaged width-alignment nibble")
    changed |= did
    return source, changed

def patch_tex(source: str) -> tuple[str, bool]:
    changed = False
    helper = """// A packaged layout's width alignment (byte 1's low nibble, log2 GOBs; 0 = none).
// It pads each tiled level's row pitch and aligns array layers independently of SPARSE.
static unsigned packaged_width_log2(const nvn_texdesc *d) {
    return d->pkg_block_h ? ((unsigned)(d->pkg_block_h - 1) >> 8) & 0xf : 0;
}
"""
    marker = "static unsigned packaged_width_log2(const nvn_texdesc *d)"
    if marker not in source:
        anchor = "static unsigned pick_tile(uint32_t gobs) { return gobs >= 16 ? 4 : gobs >= 8 ? 3 : gobs >= 4 ? 2 : gobs >= 2 ? 1 : 0; }\n"
        source, did = replace_once(source, anchor, anchor + helper, "insert packaged width decoder")
        changed |= did
    elif helper not in source:
        fail("packaged width helper exists but does not match the reviewed implementation")

    source, did = replace_once(
        source,
        "    uint32_t tw = 128u >> (sh + tileD); if (!tw) tw = 1;   // GOB columns of a 64 KB tile\n"
        "    int tiled = sparse_of(d);   // still in a sparse texture's tiled levels",
        "    unsigned pw = packaged_width_log2(d);\n"
        "    uint32_t tw = pw ? 1u << pw : 128u >> (sh + tileD); if (!tw) tw = 1;   // packaged width alignment, else 64 KB tile width\n"
        "    int tiled = sparse_of(d) || pw;   // sparse tiled levels or packaged levels with width alignment",
        "pad packaged levels to their physical GOB row pitch",
    )
    changed |= did
    source, did = replace_once(
        source,
        "        unsigned sh = th + td + 9; uint64_t g = ls >> sh;",
        "        unsigned pw = packaged_width_log2(d);\n"
        "        unsigned sh = pw ? pw + tileH + tileD + 9 : th + td + 9; uint64_t g = ls >> sh;",
        "align packaged array layers to the full physical pitch",
    )
    changed |= did

    if "pkg_block_h ? ((unsigned)(d->pkg_block_h - 1) >> 8) & 0xf" not in source:
        fail("post-patch verification: packaged width decoder missing")
    required = (
        "unsigned pw = packaged_width_log2(d);",
        "int tiled = sparse_of(d) || pw;",
        "unsigned sh = pw ? pw + tileH + tileD + 9 : th + td + 9;",
    )
    missing = [x for x in required if x not in source]
    if missing:
        fail("post-patch verification missing: " + ", ".join(missing))
    return source, changed

def patch_header(source: str) -> tuple[str, bool]:
    return replace_once(
        source,
        "    int pkg_block_h;                      // Packaged byte 0 (low nibble log2 block height, high nibble log2 block depth) + 1; 0 = use the automatic algorithm",
        "    int pkg_block_h;                      // Packed layout byte 0 (H/D) plus byte 1 low nibble (W << 8), then + 1; 0 = automatic",
        "document packed packaged layout field",
    )

def replace_optional(source: str, old: str, new: str, label: str) -> tuple[str, bool]:
    old_n, new_n = source.count(old), source.count(new)
    if old_n == 1 and new_n == 0:
        return source.replace(old, new, 1), True
    if old_n == 0 and new_n in (0, 1):
        return source, False
    fail(f"{label}: ambiguous diagnostic anchor (old={old_n}, new={new_n}).")
    raise AssertionError("unreachable")

def patch_mtl(source: str) -> tuple[str, bool]:
    # These two strings are diagnostic-only. Keep the correctness patch usable
    # even if an upstream log wording change has already updated or removed them.
    changed = False
    source, did = replace_optional(
        source,
        "block height log2 %d (packaged %d)",
        "block height log2 %d (packaged layout %#x)",
        "label packaged texture diagnostic correctly",
    )
    changed |= did
    source, did = replace_optional(
        source,
        "stride=%u block_h=%d storage %llu bytes non-zero %llu",
        "stride=%u pkg_layout=%#x storage %llu bytes non-zero %llu",
        "label texture-info diagnostic correctly",
    )
    changed |= did
    return source, changed

def patch_deswizzle(source: str) -> tuple[str, bool]:
    return replace_once(
        source,
        "// the row as laid out (padded in a sparse texture's tiled levels)",
        "// the row as laid out (padded in sparse tiled levels or packaged layouts with width alignment)",
        "document physical row pitch in deswizzle path",
    )

def patch_layout_test(source: str) -> tuple[str, bool]:
    changed = False
    source, did = replace_once(
        source,
        "counts pixel rows, also for BC. pkg is byte 0 + 1 (0 = automatic), as nvn_texdesc stores it.",
        "counts pixel rows, also for BC. pkg is the first 12 layout bits + 1 (0 = automatic), as nvn_texdesc stores it.",
        "document packaged H/D/W test encoding",
    )
    changed |= did
    anchor = "static const shape_t driver[] = {\n"
    rows = """    // Packaged H/D/W nibbles: byte 1 low nibble is the row-pitch alignment in GOBs.
    {"packaged ASTC6x6 W4",                 1,0x7d,4,2052,1026,1,1,0,0x404,0x120000,0x120000,0,512,3,0},
    {"packaged ASTC6x6 W0 control",         1,0x7d,4,2052,1026,1,1,0,0x004,0x102000,0x102000,0,512,3,0},
    {"packaged ASTC6x6 W4 mip tail",        1,0x7d,4,2052,1026,1,8,0,0x404,0x19dc00,0x19dc00,0x120000,512,3,0},
    {"packaged ASTC6x6 W4 cube tail",       8,0x7d,4,1024,1024,6,8,0,0x404,0x540000,0xe0000,0x90000,512,3,0},
    {"packaged ASTC6x6 W4 array tail",      4,0x7d,4,2052,1026,3,8,0,0x404,0x4e0000,0x1a0000,0x120000,512,3,0},
"""
    if rows.strip() not in source:
        source, did = replace_once(source, anchor, anchor + rows, "add packaged width layout regressions")
        changed |= did
    return source, changed

def patch_nvn_test(source: str) -> tuple[str, bool]:
    marker = "    // Packaged H/D/W nibbles describe physical pitch independently of API SPARSE."
    block = """    // Packaged H/D/W nibbles describe physical pitch independently of API SPARSE.
    {
        NVNtextureBuilder b = {0}; NVNpackagedTextureLayout layout={{3,4,0,0,0,0,0,0}};
        P(nvnTextureBuilderSetDevice)(&b,&dev);
        P(nvnTextureBuilderSetDefaults)(&b); P(nvnTextureBuilderSetSize2D)(&b,2052,1026);
        P(nvnTextureBuilderSetFormat)(&b,NVN_FORMAT_RGBA_ASTC_6x6); P(nvnTextureBuilderSetFlags)(&b,NVN_TEXTURE_FLAGS_IMAGE);
        P(nvnTextureBuilderSetPackagedTextureLayout)(&b,&layout);
        EXPECT("packaged width nibble reaches description",0x404,((tex_builder_t*)&b)->d.pkg_block_h);
        EXPECT("packaged full tiles use padded pitch",0x120000,P(nvnTextureBuilderGetStorageSize)(&b));
        EXPECT("packaged pitch leaves public flags unchanged",NVN_TEXTURE_FLAGS_IMAGE,P(nvnTextureBuilderGetFlags)(&b));
        NVNtextureSparseTileLayout sparse; P(nvnTextureBuilderGetSparseTileLayout)(&b,&sparse);
        EXPECT("packaged pitch does not advertise sparse tiles",0,sparse.numTiledLevels);
        layout.layout[1]=0; P(nvnTextureBuilderSetPackagedTextureLayout)(&b,&layout);
        EXPECT("ordinary packaged pitch remains unpadded",0x102000,P(nvnTextureBuilderGetStorageSize)(&b));
        P(nvnTextureBuilderSetPackagedTextureLayout)(&b,NULL);
        EXPECT("clearing packaged layout clears width too",0,((tex_builder_t*)&b)->d.pkg_block_h);
    }

"""
    if marker in source:
        if block.strip() not in source:
            fail("NVN regression block marker already exists with different content")
        return source, False
    anchor = "    // 6c. Write-protected dirty pages:"
    source, changed = replace_once(source, anchor, block + anchor, "add NVN packaged width API regression")
    return source, changed

def encode_layout(byte0: int, byte1: int) -> int:
    return (byte0 | ((byte1 & 0xf) << 8)) + 1

def width_log2(encoded: int) -> int:
    return ((encoded - 1) >> 8) & 0xf if encoded else 0

def self_test() -> None:
    packed = encode_layout(0x03, 0x04)
    assert packed == 0x404 and width_log2(packed) == 4
    blocks = (2052 + 6 - 1) // 6
    row_bytes = blocks * 16
    unpadded_gobs = (row_bytes + 63) // 64
    padded_gobs = ((unpadded_gobs + 15) // 16) * 16
    assert unpadded_gobs == 86 and padded_gobs == 96
    height_blocks = (1026 + 6 - 1) // 6
    gob_rows = (height_blocks + 7) // 8
    storage = padded_gobs * ((gob_rows + 7) // 8) * (1 << (9 + 3))
    assert storage == 0x120000
    assert unpadded_gobs * ((gob_rows + 7) // 8) * (1 << (9 + 3)) == 0x102000
    print("[KaKaRoTiOS] Packaged H/D/W encoding + 2052x1026 ASTC6x6 W4 pitch regression: OK")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.engine_root is None:
        parser.error("--engine-root is required unless --self-test is used")

    engine = args.engine_root.resolve()
    pin_file = engine.parent / ".upstream-ref"
    if not pin_file.is_file() or pin_file.read_text(encoding="utf-8").strip() != ENGINE_PIN:
        fail(f"engine pin must be exactly {ENGINE_PIN}.")
    handlers = (
        ("dm/gfx/nvn/hle_nvn.c", patch_hle),
        ("dm/gfx/nvn/nvn_tex.c", patch_tex),
        ("dm/gfx/nvn/nvn_tex.h", patch_header),
        ("dm/gfx/nvn/nvn_mtl.m", patch_mtl),
        ("dm/gfx/tex/nvn_deswizzle.c", patch_deswizzle),
        ("dm/gfx/tests/t_tex_layout.c", patch_layout_test),
        ("dm/gfx/tests/t_nvn.c", patch_nvn_test),
    )
    changed_files = []
    for rel, handler in handlers:
        path = engine / rel
        if not path.is_file():
            fail(f"pinned source file is missing: {path}")
        original = path.read_text(encoding="utf-8")
        patched, changed = handler(original)
        if changed:
            if args.check_only:
                changed_files.append(rel + " (would patch)")
            else:
                tmp = path.with_suffix(path.suffix + ".kakarot-tmp")
                tmp.write_text(patched, encoding="utf-8")
                os.replace(tmp, path)
                changed_files.append(rel)
    if args.check_only:
        if changed_files:
            fail("patch has not yet been applied: " + ", ".join(changed_files))
        print("[KaKaRoTiOS] Packaged texture width-alignment patch: already applied and verified.")
    else:
        print("[KaKaRoTiOS] Packaged texture width-alignment backport: " +
              (", ".join(changed_files) if changed_files else "already applied; source unchanged"))
        print("[KaKaRoTiOS] Runtime texture pitch/mip/layer layout corrected; shader package and cached Metal image untouched.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
