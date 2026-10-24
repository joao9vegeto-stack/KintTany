#!/usr/bin/env python3
"""Convert iOS SPU_PIC_CAPTURE rows into address-independent native C lifts.

Inputs are private files supplied by the user: the game's decrypted ELF,
runtime captures exported by AscensionRecomp, and the pinned gowa-fixes
PS3Recomp tools checkout. Generated C is placed below runtime/m793-spu-pic;
the iOS build compiles and registers it explicitly. No SELF, RAP, or ELF is
copied into this repository by this script.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import sys

EXPECTED_PS3RECOMP = "f6ab60baf37662bd712592b7ef9f66891972a5fc"


def locate(blob: bytes, haystack: bytes) -> list[int]:
    found: list[int] = []
    start = 0
    while True:
        at = haystack.find(blob, start)
        if at < 0:
            return found
        found.append(at)
        start = at + 1


def read_capture(path: Path, overlays: set[int]) -> list[bytes]:
    rows: list[bytes] = []
    for line_no, line in enumerate(path.read_text(errors="strict").splitlines(), 1):
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            _pc = int(fields[0], 16)
            overlay = int(fields[1], 10)
            code = bytes.fromhex(fields[2])
        except ValueError as error:
            raise SystemExit(f"{path}:{line_no}: malformed PIC capture row: {error}")
        if _pc < 0 or _pc >= 0x40000 or len(code) != 64:
            raise SystemExit(f"{path}:{line_no}: invalid LS address or code length")
        if overlays and overlay not in overlays:
            continue
        rows.append(code)
    return rows


def clusters(offsets: list[int], gap: int, max_span: int) -> list[list[int]]:
    result: list[list[int]] = []
    current: list[int] = []
    for offset in offsets:
        if current and (offset - current[-1] > gap or offset - current[0] > max_span):
            result.append(current)
            current = []
        current.append(offset)
    if current:
        result.append(current)
    return result


def lift_region(ps3recomp: Path, elf_data: bytes, start: int, end: int,
                seeds: list[int], name: str, target: Path) -> str:
    sys.path.insert(0, str(ps3recomp / "tools"))
    from wrap_spu_elf import wrap

    work = target / name
    work.mkdir(parents=True, exist_ok=True)
    prefix = name + "_"
    region = elf_data[start:end]
    temporary_elf = work / "_region.elf"
    temporary_elf.write_bytes(wrap(region, base=0, entry=seeds[0]))
    command = [sys.executable, str(ps3recomp / "tools/spu_lifter.py"),
               "--auto-functions", str(temporary_elf), "--base", "0", "--pic",
               "--symbol-prefix", prefix, "-o", str(work),
               "--source-name", "spu_recomp.c", "--header-name", "spu_recomp.h",
               "--extra-funcs", ",".join(hex(seed) for seed in seeds)]
    result = subprocess.run(command, capture_output=True, text=True)
    temporary_elf.unlink(missing_ok=True)
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout or "SPU PIC lifter failed")

    # The upstream lifter assumes its output is two levels below the repo
    # root (under spu/). This project stores generated lifts under runtime/;
    # resolve the two runtime headers through the include paths passed by the
    # iOS builder instead of leaving those now-invalid relative paths.
    header = work / "spu_recomp.h"
    header_text = header.read_text()
    header_anchor = '#include "../../runtime/spu/spu_context.h"'
    if header_anchor not in header_text:
        raise SystemExit("PIC lifter header no longer has the expected runtime include")
    header.write_text(header_text.replace(header_anchor, '#include "spu_context.h"', 1))
    source = work / "spu_recomp.c"
    source_text = source.read_text()
    helper_anchor = '#include "../../runtime/spu/spu_helpers.h"'
    if helper_anchor not in source_text:
        raise SystemExit("PIC lifter source no longer has the expected helper include")
    source.write_text(source_text.replace(helper_anchor, '#include "spu_helpers.h"', 1))
    if "spu_unsupported(" in source_text:
        raise SystemExit(f"{name}: lifter emitted unsupported SPU instructions; refusing native registration")

    rows = [", ".join(f"0x{byte:02X}" for byte in region[i:i + 16])
            for i in range(0, len(region), 16)]
    registration = [
        "",
        f"static const uint8_t {prefix}region[{len(region)}] = {{",
        *(f"    {row}," for row in rows),
        "};",
        "",
        f"void {prefix}register(void)",
        "{",
        f"    spu_pic_register({prefix}pic_functions, {prefix}pic_function_count, "
        f"{prefix}region, {len(region)}u, 0);",
        "}",
        "",
    ]
    with source.open("a") as stream:
        stream.write("\n".join(registration))
    (work / "region.txt").write_text(
        f"elf_offset=0x{start:X} size=0x{end - start:X} seeds={len(seeds)}\n")
    stats = "; ".join(line.strip() for line in result.stdout.splitlines()
                       if "function(s)" in line or "unsupported" in line)
    print(f"{name}: ELF 0x{start:X}..0x{end:X}, {len(seeds)} captured entries; {stats}")
    return f"{prefix}register"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--ps3recomp", required=True, type=Path,
                        help="checkout of the PS3Recomp gowa-fixes branch")
    parser.add_argument("--elf", required=True, type=Path,
                        help="private decrypted GOWA.ELF matching this installation")
    parser.add_argument("--out", type=Path,
                        default=Path("runtime/m793-spu-pic"))
    parser.add_argument("--gap", type=lambda value: int(value, 0), default=0x8000)
    parser.add_argument("--margin", type=lambda value: int(value, 0), default=0x800)
    parser.add_argument("--min-entries", type=int, default=1,
                        help="minimum ELF-backed capture entries per region (default: 1)")
    parser.add_argument("--overlay", action="append", type=int, default=[])
    args = parser.parse_args()

    ps3recomp, elf_path, out = (path.resolve() for path in
                                (args.ps3recomp, args.elf, args.out))
    actual = subprocess.check_output(
        ["git", "-C", str(ps3recomp), "rev-parse", "HEAD"], text=True).strip()
    if actual != EXPECTED_PS3RECOMP:
        raise SystemExit(f"PS3Recomp PIC lifter pin mismatch: {actual} != {EXPECTED_PS3RECOMP}")
    elf = elf_path.read_bytes()
    if (len(elf) < 64 or elf[:4] != b"\x7fELF" or elf[4:6] != b"\x02\x02" or
            struct.unpack_from(">H", elf, 18)[0] != 21):
        raise SystemExit("--elf must be the matching ELF64 big-endian GOWA.ELF")

    code_blobs: set[bytes] = set()
    for capture_path in args.captures:
        code_blobs.update(read_capture(capture_path.resolve(), set(args.overlay)))
    offsets = sorted({offset for blob in code_blobs for offset in locate(blob, elf)})
    missing = sum(1 for blob in code_blobs if not locate(blob, elf))
    if not offsets:
        raise SystemExit("no captured 64-byte fragment matched the supplied GOWA.ELF")
    print(f"PIC capture mapping: {len(code_blobs)} unique fragments, "
          f"{len(offsets)} ELF offsets, {missing} fragments not in the ELF")

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("pic_*"):
        if old.is_dir():
            shutil.rmtree(old)
    functions: list[str] = []
    max_region = 0x3F000
    max_seed_span = max_region - 2 * args.margin - 64
    if max_seed_span <= 0:
        raise SystemExit("--margin leaves no room for a captured SPU fragment")
    for group in clusters(offsets, args.gap, max_seed_span):
        if len(group) < args.min_entries:
            continue
        start = max(0, (group[0] - args.margin) & ~0xF)
        end = min(len(elf), (group[-1] + 64 + args.margin + 0xF) & ~0xF)
        if end - start > max_region:
            end = start + max_region
        seeds = sorted({offset - start for offset in group
                        if start <= offset and offset + 64 <= end})
        if not seeds:
            continue
        name = f"pic_{start:08X}"
        functions.append(lift_region(ps3recomp, elf, start, end, seeds, name, out))
    if not functions:
        raise SystemExit("captures matched the ELF, but no region met --min-entries")

    registry = ["/* Generated by tools/m793_lift_spu_pic.py. */",
                *(f"extern void {function}(void);" for function in functions),
                "void ascension_spu_pic_register_all(void)", "{",
                *(f"    {function}();" for function in functions), "}", ""]
    (out / "spu_pic_registry.c").write_text("\n".join(registry))
    print(f"Generated {len(functions)} address-independent PIC region(s) in {out}")


if __name__ == "__main__":
    main()
