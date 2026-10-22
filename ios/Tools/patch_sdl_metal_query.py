#!/usr/bin/env python3
"""Patch the EXACT SDL 3.4.18 Metal GPU source with reSOT's query ABI.

Usage: python3 patch_sdl_metal_query.py /path/to/SDL3-3.4.18

All anchors must be uniquely present. No silent version drift. Source is copied
in place only after all anchors pass. The original SDL zlib header is kept.
"""
from pathlib import Path
import argparse
import hashlib
import sys


def replace_once(source, old, new):
    assert source.count(old) == 1, f"SDL source anchor mismatch: {old[:90]!r} (found {source.count(old)})"
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    if 'PoPTST Metal native query' in source:
        raise ValueError('already patched')
    # Forward declarations; query struct is fully defined by the injected .inc.
    source = replace_once(source,
        'typedef struct MetalCommandBuffer\n{',
        '/* PoPTST Metal native query: one exact sample-count result per pass. */\n'
        'typedef struct ResotMetalQuery ResotMetalQuery;\n'
        'typedef struct MetalCommandBuffer MetalCommandBuffer;\n'
        'static void resot_metal_attach_query(MetalCommandBuffer *c, MTLRenderPassDescriptor *d);\n'
        'typedef struct MetalCommandBuffer\n{')
    source = replace_once(source,
        '    // Render Pass\n    id<MTLRenderCommandEncoder> renderEncoder;',
        '    // Render Pass\n    ResotMetalQuery *resotPendingQuery;\n'
        '    ResotMetalQuery *resotActiveQuery;\n'
        '    id<MTLRenderCommandEncoder> renderEncoder;')
    source = replace_once(source,
        '        commandBuffer->graphics_pipeline = NULL;\n        commandBuffer->compute_pipeline = NULL;',
        '        commandBuffer->graphics_pipeline = NULL;\n'
        '        commandBuffer->compute_pipeline = NULL;\n'
        '        commandBuffer->resotPendingQuery = NULL;\n'
        '        commandBuffer->resotActiveQuery = NULL;')
    source = replace_once(source,
        '        metalCommandBuffer->renderEncoder = [metalCommandBuffer->handle renderCommandEncoderWithDescriptor:passDescriptor];',
        '        resot_metal_attach_query(metalCommandBuffer, passDescriptor);\n'
        '        metalCommandBuffer->renderEncoder = [metalCommandBuffer->handle renderCommandEncoderWithDescriptor:passDescriptor];')
    source = replace_once(source,
        '        [metalCommandBuffer->renderEncoder endEncoding];\n        metalCommandBuffer->renderEncoder = nil;\n\n        for (Uint32 i = 0; i < MAX_VERTEX_BUFFERS; i += 1)',
        '        [metalCommandBuffer->renderEncoder endEncoding];\n'
        '        metalCommandBuffer->renderEncoder = nil;\n'
        '        metalCommandBuffer->resotActiveQuery = NULL;\n\n'
        '        for (Uint32 i = 0; i < MAX_VERTEX_BUFFERS; i += 1)')
    source = replace_once(source,
        '    // End any active passes\n    if (commandBuffer->renderEncoder)',
        '    // End any active passes\n'
        '    commandBuffer->resotPendingQuery = NULL;\n'
        '    commandBuffer->resotActiveQuery = NULL;\n'
        '    if (commandBuffer->renderEncoder)')
    source = replace_once(source,
        'SDL_GPUBootstrap MetalDriver = {',
        '#include "resot_query_metal.inc"\n\n'
        'SDL_GPUBootstrap MetalDriver = {')
    assert source.count('#include "resot_query_metal.inc"') == 1
    return source


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sdl_root', type=Path)
    ap.add_argument('--check-only', action='store_true')
    args = ap.parse_args()
    source = args.sdl_root / 'src/gpu/metal/SDL_gpu_metal.m'
    if not source.is_file():
        sys.exit(f'SDL Metal source unavailable: {source}')
    original = source.read_text()
    try:
        transformed = patch(original)
    except (ValueError, AssertionError) as exc:
        sys.exit(f'REFUSE SDL SOURCE MODIFICATION: {exc}')
    if args.check_only:
        print('SDL 3.4.18 Metal GPU anchors: PASS, not modified')
        return
    include = Path(__file__).parent / 'resot_query_metal.inc'
    header = Path(__file__).parent / 'resot_gpu_query.h'
    if not include.is_file() or not header.is_file():
        sys.exit('Missing query implementation/header; no modification made')
    # Write once we have checked both sources and the backend symbol.
    assert 'RESOT_GetMetalQueryAPI' in include.read_text()
    dest = source.parent / 'resot_query_metal.inc'
    hdr = source.parent / 'resot_gpu_query.h'
    if dest.exists() or hdr.exists():
        sys.exit('Refuse overwrite existing Metal query extension files')
    dest.write_bytes(include.read_bytes())
    hdr.write_bytes(header.read_bytes())
    source.write_text(transformed)
    print('PoPTST patched SDL GPU Metal driver')
    print('Source SHA-256:', hashlib.sha256(source.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
