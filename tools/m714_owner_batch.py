#!/usr/bin/env python3
"""PRIVATE offline owner-ELF batch planner for native PPU AOT.

Inputs: original owner-supplied ELF and a list of frontier PCs. Reads only
bounded executable PT_LOAD bytes, emits only verified candidate function
ranges, and rejects unsupported ISA/CFG. Never uploads original ELF or code.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ppu_cfg_lifter import PPUImage, Unsupported, lift

MAX_SEEDS = 8192
MAX_WORDS = 512


def terminal_word(w: int) -> bool:
    op = w >> 26
    if op == 18 and not (w & 1):
        return True
    if op == 19 and ((w >> 1) & 1023) in (16, 528) and not (w & 1):
        return ((w >> 21) & 31) in (20, 21, 22, 23, 28, 29, 30, 31)
    return False


def find_aot_window(image: PPUImage, pc: int, max_words: int) -> tuple[dict | None, str]:
    if not 0 < pc <= 0xFFFFFFFC or pc & 3:
        return None, 'unaligned/out-of-range PC'
    words = []
    for size in range(1, max_words + 1):
        try:
            word = image.words(pc + 4 * (size - 1), pc + 4 * size)[0]
        except (Unsupported, ValueError, IndexError) as exc:
            return None, f'executable range unavailable: {type(exc).__name__}'
        words.append(word)
        if terminal_word(word):
            try:
                _, counts = lift(words, pc, f'ar_game_ppu_{pc:08x}')
                return {'start': f'0x{pc:08x}', 'end': f'0x{pc+size*4:08x}',
                        'instructions': size, 'opcodes': counts}, ''
            except Unsupported as exc:
                return None, f'unsupported ISA/CFG: {exc}'
    return None, 'no provable terminator within bounded window'


def plan(image: PPUImage, seeds: list[int], max_words: int = 256) -> dict:
    if not 1 <= len(seeds) <= MAX_SEEDS or not 1 <= max_words <= MAX_WORDS:
        raise ValueError('unbounded seed list / instruction budget')
    if len(seeds) != len(set(seeds)):
        raise ValueError('duplicate guest PC')
    accepted, rejected = [], []
    for pc in sorted(seeds):
        item, error = find_aot_window(image, pc, max_words)
        if item is None:
            rejected.append({'pc': f'0x{pc:08x}', 'reason': error})
        else:
            accepted.append(item)
    return {'schema': 'ascensionrecomp/m714-private-batch-v1',
            'requested': len(seeds), 'accepted': accepted,
            'rejected': rejected,
            'notice': 'Private derived PPC code; candidates are not proof of boot, RSX or gameplay.'}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--elf', type=Path, required=True)
    cli.add_argument('--pcs-json', type=Path, required=True,
                     help='Private JSON array of guest PC strings, e.g. ["0x003c4db4"]')
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--max-words', type=int, default=256)
    cli.add_argument('--emit-private-aot', action='store_true',
                     help='Generate separate owner-only AOT C for accepted full windows')
    args = cli.parse_args()
    if not args.elf.is_file():
        cli.error('Original private ELF path does not exist')
    seeds_raw = json.loads(args.pcs_json.read_text())
    if not isinstance(seeds_raw, list) or any(not isinstance(x, (str, int)) for x in seeds_raw):
        cli.error('Expected JSON array of unsigned guest PC strings/ints')
    seeds = [int(x, 0) if isinstance(x, str) else x for x in seeds_raw]
    report = plan(PPUImage(args.elf), seeds, args.max_words)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = [{'start': x['start'], 'end': x['end']} for x in report['accepted']]
    (args.out / 'batch-functions.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (args.out / 'batch-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.emit_private_aot and manifest:
        from ppu_aot_build import build
        build(args.elf, args.out / 'batch-functions.json', args.out / 'PRIVATE-AOT')
    print(f"M7.14 owner batch candidates={len(manifest)}/{len(seeds)}; original ELF stays local")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
