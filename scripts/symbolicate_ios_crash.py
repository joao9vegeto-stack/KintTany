#!/usr/bin/env python3
"""Disassemble Bananza crash offsets from the embedded NXNative iOS Mach-O."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path
from typing import BinaryIO

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
CPU_TYPE_ARM64 = 0x0100000C
FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF


def name(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace")


def parse_thin(fp: BinaryIO, base: int, slice_size: int | None = None):
    fp.seek(base)
    header = fp.read(32)
    if len(header) != 32:
        raise ValueError("truncated Mach-O header")
    magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack(
        "<IiiIIIII", header
    )
    if magic != MH_MAGIC_64:
        raise ValueError(f"expected 64-bit little-endian Mach-O, got 0x{magic:08x}")
    commands = fp.read(sizeofcmds)
    if len(commands) != sizeofcmds:
        raise ValueError("truncated Mach-O load commands")

    sections = {}
    pos = 0
    for _ in range(ncmds):
        if pos + 8 > len(commands):
            raise ValueError("invalid load-command table")
        cmd, cmdsize = struct.unpack_from("<II", commands, pos)
        if cmdsize < 8 or pos + cmdsize > len(commands):
            raise ValueError("invalid Mach-O load-command size")
        if cmd == LC_SEGMENT_64:
            if cmdsize < 72:
                raise ValueError("short LC_SEGMENT_64")
            segname = name(commands[pos + 8:pos + 24])
            nsects = struct.unpack_from("<I", commands, pos + 64)[0]
            secpos = pos + 72
            if secpos + nsects * 80 > pos + cmdsize:
                raise ValueError(f"section table outside segment {segname}")
            for _s in range(nsects):
                raw = commands[secpos:secpos + 80]
                sectname = name(raw[:16])
                section_segname = name(raw[16:32])
                addr, size = struct.unpack_from("<QQ", raw, 32)
                offset = struct.unpack_from("<I", raw, 48)[0]
                section_flags = struct.unpack_from("<I", raw, 64)[0]
                # S_ZEROFILL / S_GB_ZEROFILL / S_THREAD_LOCAL_ZEROFILL have no file bytes.
                section_type = section_flags & 0xFF
                zerofill = section_type in (0x1, 0xC, 0x12)
                if not zerofill and slice_size is not None and offset + size > slice_size:
                    raise ValueError(f"section {section_segname},{sectname} exceeds its architecture slice")
                sections[(section_segname, sectname)] = {
                    "segment": section_segname,
                    "name": sectname,
                    "address": addr,
                    "size": size,
                    "file_offset": base + offset,
                    "flags": section_flags,
                }
                secpos += 80
        pos += cmdsize
    return cputype, cpusubtype, sections


def parse_macho_sections(path: Path):
    with path.open("rb") as fp:
        first = fp.read(8)
        if len(first) < 4:
            raise ValueError("file is too short to be Mach-O")
        magic_be = struct.unpack(">I", first[:4])[0]
        if magic_be in (FAT_MAGIC, FAT_MAGIC_64):
            nfat = struct.unpack(">I", first[4:8])[0]
            archs = []
            fp.seek(8)
            for _ in range(nfat):
                if magic_be == FAT_MAGIC:
                    raw = fp.read(20)
                    if len(raw) != 20:
                        raise ValueError("truncated FAT_ARCH table")
                    cputype, cpusubtype, offset, size, align = struct.unpack(">iiIII", raw)
                else:
                    raw = fp.read(32)
                    if len(raw) != 32:
                        raise ValueError("truncated FAT_ARCH_64 table")
                    cputype, cpusubtype, offset, size, align, reserved = struct.unpack(">iiQQII", raw)
                archs.append((cputype, cpusubtype, offset, size))
            matching = [a for a in archs if a[0] == CPU_TYPE_ARM64]
            if not matching:
                raise ValueError("universal Mach-O has no arm64 slice")
            cputype, cpusubtype, base, size = matching[0]
            parsed_type, parsed_subtype, sections = parse_thin(fp, base, size)
        else:
            fp.seek(0)
            parsed_type, parsed_subtype, sections = parse_thin(fp, 0, path.stat().st_size)
        if parsed_type != CPU_TYPE_ARM64:
            raise ValueError(f"Mach-O slice is not arm64 (cputype 0x{parsed_type:x})")
        return parsed_type, parsed_subtype, sections


def disassemble_window(fp: BinaryIO, section: dict, module: str, offset: int, md,
                       *, before: int, after: int, label: str) -> list[str]:
    lo = max(0, offset - before) & ~3
    hi = min(section["size"], offset + after)
    if offset >= section["size"]:
        return [f"  {module}+0x{offset:x}: OUTSIDE {section['name']} (section size 0x{section['size']:x})"]
    fp.seek(section["file_offset"] + lo)
    code = fp.read(hi - lo)
    lines = [f"\n[{label}] {module}+0x{offset:08x}; window +0x{lo:x}..+0x{hi:x}"]
    if len(code) != hi - lo:
        return lines + ["  ERROR: code section bytes are truncated in the Mach-O"]
    decoded = list(md.disasm(code, lo))
    if not decoded:
        return lines + ["  ERROR: Capstone could not decode instructions at this offset"]
    for ins in decoded:
        marks = []
        if ins.address == offset:
            marks.append("TARGET")
        if ins.address == offset - 4 and label in ("LR return address", "backtrace return address"):
            marks.append("CALLSITE? LR-4")
        mark = "  <== " + ", ".join(marks) if marks else ""
        lines.append(f"  {module}+0x{ins.address:08x}: {ins.bytes.hex():<8} {ins.mnemonic:<9} {ins.op_str}{mark}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--macho", type=Path, required=True, help="DmGame framework Mach-O executable")
    ap.add_argument("--output", type=Path, required=True, help="text report path")
    args = ap.parse_args()
    report = [
        "NXNative embedded ARM64 crash-site disassembly",
        "Crash: SIGSEGV addr=0, PC=sdk+0x702920, LR=main+0x48a5d8, x0=0, x2=0x60.",
        "gen_embed.py places original module text at module offset 0 in __TEXT,__dm<module>x0.",
        f"Mach-O: {args.macho}",
    ]
    try:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        cputype, cpusubtype, sections = parse_macho_sections(args.macho)
        report.append(f"CPU: arm64 cputype=0x{cputype:x} subtype={cpusubtype}")
        for module in ("main", "sdk"):
            key = ("__TEXT", f"__dm{module}x0")
            section = sections.get(key)
            if section:
                report.append(
                    f"Section {key[0]},{key[1]}: vmaddr=0x{section['address']:x} "
                    f"size=0x{section['size']:x} fileoff=0x{section['file_offset']:x}"
                )
            else:
                report.append(f"MISSING SECTION {key[0]},{key[1]}")
        # The constructor's vtable lives in main's writable embedded image, not x0.
        main_text = sections.get(("__TEXT", "__dmmainx0"))
        main_data = sections.get(("__DMmainW", "__img"))
        if main_text and main_data:
            module_data_off = main_data["address"] - main_text["address"]
            report.append(
                f"Section __DMmainW,__img: vmaddr=0x{main_data['address']:x} "
                f"size=0x{main_data['size']:x} fileoff=0x{main_data['file_offset']:x} "
                f"module_offset=0x{module_data_off:x}"
            )
            vtable_off = 0x2426EE0
            local = vtable_off - module_data_off
            if 0 <= local and local + 0x80 <= main_data["size"]:
                with args.macho.open("rb") as data_fp:
                    data_fp.seek(main_data["file_offset"] + local)
                    raw = data_fp.read(0x80)
                report.append(f"main vtable data main+0x{vtable_off:x} (raw, pre-relocation):")
                for off in range(0, len(raw), 8):
                    value = struct.unpack_from("<Q", raw, off)[0]
                    report.append(f"  +0x{off:02x}: 0x{value:016x}")
                # These are the virtual slots called by main+0x48a584 / +0x48a5d4.
                for slot in (0x28, 0x40):
                    value = struct.unpack_from("<Q", raw, slot)[0]
                    report.append(f"  vtable slot +0x{slot:x}: raw target 0x{value:x}")
                    if 0 < value < main_text["size"]:
                        with args.macho.open("rb") as code_fp:
                            report.extend(disassemble_window(
                                code_fp, main_text, "main", value, md,
                                before=0x40, after=0x100,
                                label=f"vtable slot +0x{slot:x} target",
                            ))
            else:
                report.append(
                    f"vtable main+0x{vtable_off:x} is outside __DMmainW,__img "
                    f"(local offset 0x{local:x})"
                )
        else:
            report.append("MISSING MAIN DATA SECTION __DMmainW,__img or __TEXT,__dmmainx0")
        sites = [
            # Trace the caller that constructed the null memcpy destination.
            ("main", 0x48A390, "caller function around null destination", 0x180, 0x280),
            ("main", 0x489620, "object preparation before caller", 0x100, 0x180),
            ("main", 0x4810E8, "caller of object preparation", 0x100, 0x180),
            ("main", 0x488ED4, "caller of main+0x4811c4", 0x100, 0x180),
            ("main", 0x1B7B210, "memcpy tail-call helper", 0x40, 0x100),
            ("main", 0x5259C0, "helper called before memcpy", 0x100, 0x180),
            ("main", 0x2621C0, "allocation helper", 0x100, 0x180),
            ("main", 0x4788CC, "constructor of the 0x90-byte object", 0x100, 0x240),
            ("main", 0x17580C, "object registration / initialization helper", 0x100, 0x240),
            ("main", 0x453B10, "object setup helper", 0x80, 0x180),
            ("main", 0x51DA40, "object setup helper 2", 0x80, 0x180),
            ("main", 0x4A9918, "object setup helper 3", 0x80, 0x180),
            ("main", 0x288EA0, "guest allocator entry", 0x100, 0x240),
            ("sdk", 0x702920, "CRASH PC", 0x40, 0x40),
            ("main", 0x48A5D8, "LR return address", 0x40, 0x28),
            ("main", 0x48909C, "backtrace return address", 0x20, 0x10),
            ("main", 0x4811C4, "backtrace return address", 0x10, 0x08),
            ("main", 0x47E260, "backtrace return address", 0x10, 0x08),
            ("main", 0x477994, "backtrace return address", 0x10, 0x08),
            ("main", 0x476E0C, "backtrace return address", 0x10, 0x08),
            ("main", 0x45EA64, "backtrace return address", 0x10, 0x08),
            ("main", 0x45E860, "backtrace return address", 0x10, 0x08),
            ("main", 0x45DBB4, "backtrace return address", 0x10, 0x08),
            ("main", 0x3CD570, "backtrace return address", 0x10, 0x08),
            ("main", 0x3C7C68, "backtrace return address", 0x10, 0x08),
            ("main", 0x6908C0, "backtrace return address", 0x10, 0x08),
            ("main", 0x828C2C, "backtrace return address", 0x10, 0x08),
            ("main", 0x5FE9CC, "backtrace return address", 0x10, 0x08),
            ("main", 0x158B680, "backtrace return address", 0x10, 0x08),
            ("sdk", 0x149CD0, "backtrace return address", 0x10, 0x08),
            ("sdk", 0x150818, "backtrace return address", 0x10, 0x08),
        ]
        with args.macho.open("rb") as fp:
            for module, offset, label, before, after in sites:
                section = sections.get(("__TEXT", f"__dm{module}x0"))
                if not section:
                    continue
                report.extend(disassemble_window(
                    fp, section, module, offset, md,
                    before=before, after=after, label=label,
                ))
    except Exception as exc:
        # Optional audit only: do not fail the profile repack if one Mach-O variant cannot be decoded.
        report.extend(["", f"SYMBOLICATION_UNAVAILABLE: {type(exc).__name__}: {exc}"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Crash-site disassembly report: {args.output} ({args.output.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
