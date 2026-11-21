#!/usr/bin/env python3
"""Export only the Dagor SPIR-V shader dump from a validated DMROMFS1 image.

This reads a single asset from the mounted RomFS by bounded index offsets:
no NSP extraction, no game saves, and no other game files are exported.
For diagnostics during the current BladesTime investigation.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

HEAD = struct.Struct('<8sQQQ')
ENT = struct.Struct('<QQIHBB')
NAME = 'compiledShaders/gameSpirV.ps50.shdump.bin'
MAX_SIZE = 256 * 1024 * 1024


def extract(image_path: Path, output_path: Path) -> dict:
    with image_path.open('rb') as fd:
        magic, index_at, index_size, count = HEAD.unpack(fd.read(HEAD.size))
        total = image_path.stat().st_size
        if (magic != b'DMROMFS1' or not 1 <= count <= 1_000_000 or
                index_at < HEAD.size or index_at > total or
                index_size != total - index_at or count * ENT.size > index_size):
            raise ValueError('invalid DMROMFS1 index')
        fd.seek(index_at)
        index = fd.read(index_size)
        if len(index) != index_size:
            raise ValueError('short DMROMFS1 index')
        names = index[count * ENT.size:]
        def ent(k):
            if not 0 <= k < count: raise ValueError('invalid RomFS entry index')
            return ENT.unpack_from(index, k * ENT.size)
        k = 0
        for component in NAME.split('/'):
            off, length, _, _, kind, _ = ent(k)
            if kind != 0 or off + length > count: raise ValueError('invalid parent directory')
            selected = None
            for child in range(off, off + length):
                _a, _b, name_at, name_len, _kind, _flags = ent(child)
                if name_at + name_len > len(names): raise ValueError('invalid name span')
                if names[name_at:name_at + name_len].decode('utf-8') == component:
                    selected = child
                    break
            if selected is None: raise FileNotFoundError(NAME)
            k = selected
        start, length, _, _, kind, flags = ent(k)
        if kind != 1 or flags or length > MAX_SIZE or start + length > index_at:
            raise ValueError('shader dump missing, marked damaged, or too large')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        written = 0
        fd.seek(start)
        with output_path.open('wb') as dest:
            while written < length:
                block = fd.read(min(8 * 1024 * 1024, length - written))
                if not block: raise ValueError('short shader dump')
                h.update(block); dest.write(block); written += len(block)
        with output_path.open('rb') as f:
            sample = f.read(min(256, length))
        result = {'name': NAME, 'size': length, 'sha256': h.hexdigest(),
                  'header_hex': sample[:64].hex(),
                  'zstd_frame_magic_in_first_256': sample.count(b'\\x28\\xb5\\x2f\\xfd'),
                  'spirv_magic_in_first_256': sample.count(b'\\x03\\x02\\x23\\x07')}
        output_path.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(extract(args.image, args.output), indent=2), flush=True)


if __name__ == '__main__': main()
