#!/usr/bin/env python3
"""Reject unresolved weak dyld binds for XOWUE's AOT guest functions."""
from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path

MACHO_MAGIC_64 = 0xFEEDFACF
LC_SYMTAB = 0x2
LC_DYLD_CHAINED_FIXUPS = 0x80000034
N_TYPE = 0x0E
N_UNDF = 0x00
N_SECT = 0x0E
N_WEAK_DEF = 0x0080
N_WEAK_REF = 0x0040
GUEST_SYMBOL = re.compile(rb"sub_[0-9A-Fa-f]{8}")


def parse_macho(path: Path) -> tuple[int, int, list[str]]:
    data = path.read_bytes()
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] != MACHO_MAGIC_64:
        raise SystemExit(f"{path} is not a little-endian 64-bit Mach-O slice")
    ncmds = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    symtab = None
    fixups = None
    for _ in range(ncmds):
        if offset + 8 > len(data):
            raise SystemExit("truncated Mach-O load command")
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or offset + size > len(data):
            raise SystemExit("invalid Mach-O load command size")
        if command == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", data, offset + 8)
            symtab = (symoff, nsyms, stroff, strsize)
        elif command == LC_DYLD_CHAINED_FIXUPS:
            dataoff, datasize = struct.unpack_from("<II", data, offset + 8)
            fixups = (dataoff, datasize)
        offset += size
    if symtab is None or fixups is None:
        raise SystemExit("Mach-O is missing LC_SYMTAB or LC_DYLD_CHAINED_FIXUPS")

    symoff, nsyms, stroff, strsize = symtab
    if symoff + nsyms * 16 > len(data) or stroff + strsize > len(data):
        raise SystemExit("Mach-O symbol table exceeds file bounds")
    strings = data[stroff : stroff + strsize]
    aot_symbols = 0
    weak_definitions = []
    weak_references = []
    strong_definitions = 0
    for index in range(nsyms):
        strx, n_type, _n_sect, n_desc, _value = struct.unpack_from("<IBBHQ", data, symoff + index * 16)
        if strx == 0 or strx >= strsize:
            continue
        end = strings.find(b"\0", strx)
        name = strings[strx : end if end >= 0 else strsize]
        if not GUEST_SYMBOL.search(name):
            continue
        aot_symbols += 1
        symbol_type = n_type & N_TYPE
        if symbol_type == N_SECT and n_desc & N_WEAK_DEF:
            weak_definitions.append(name.decode("utf-8", "replace"))
        elif symbol_type == N_SECT:
            strong_definitions += 1
        elif symbol_type == N_UNDF and n_desc & N_WEAK_REF:
            weak_references.append(name.decode("utf-8", "replace"))

    dataoff, datasize = fixups
    if dataoff + min(datasize, 28) > len(data) or datasize < 28:
        raise SystemExit("invalid chained-fixups data range")
    _version, _starts, imports_offset, symbols_offset, import_count, import_format, symbols_format = struct.unpack_from(
        "<7I", data, dataoff
    )
    if symbols_format != 0:
        raise SystemExit(f"unsupported chained-fixups symbol format {symbols_format}")
    entry_sizes = {1: 4, 2: 8, 3: 16}
    entry_size = entry_sizes.get(import_format)
    if entry_size is None or import_count > 1_000_000:
        raise SystemExit(f"unsupported chained import format/count: {import_format}/{import_count}")
    imports = dataoff + imports_offset
    symbols = dataoff + symbols_offset
    if imports + import_count * entry_size > dataoff + datasize or symbols > dataoff + datasize:
        raise SystemExit("chained-fixups import table exceeds file bounds")
    weak_dynamic_binds = []
    for index in range(import_count):
        item = imports + index * entry_size
        if import_format in (1, 2):
            word = struct.unpack_from("<I", data, item)[0]
            ordinal = word & 0xFF
            if ordinal & 0x80:
                ordinal -= 0x100
            weak_import = (word >> 8) & 1
            name_offset = word >> 9
        else:
            word = struct.unpack_from("<Q", data, item)[0]
            ordinal = word & 0xFFFF
            if ordinal & 0x8000:
                ordinal -= 0x10000
            weak_import = (word >> 16) & 1
            name_offset = (word >> 32) & 0xFFFFFFFF
        name_start = symbols + name_offset
        if name_start >= dataoff + datasize:
            raise SystemExit("chained-fixups import name exceeds file bounds")
        name_end = data.find(b"\0", name_start, dataoff + datasize)
        if name_end < 0:
            raise SystemExit("unterminated chained-fixups import name")
        name = data[name_start:name_end]
        if GUEST_SYMBOL.search(name) and (weak_import or ordinal == -3):
            weak_dynamic_binds.append((index, ordinal, name.decode("utf-8", "replace")))

    if aot_symbols < 10_000 or strong_definitions < 10_000:
        raise SystemExit(
            f"unexpectedly few linked AOT symbols: all={aot_symbols}, strong={strong_definitions}"
        )
    if weak_definitions or weak_references or weak_dynamic_binds:
        raise SystemExit(
            "AOT guest aliases are still weak or dynamically unresolved: "
            f"weak_definitions={len(weak_definitions)}, weak_references={len(weak_references)}, "
            f"weak_dyld_binds={len(weak_dynamic_binds)}; "
            f"examples={(weak_definitions + weak_references)[:3]} {weak_dynamic_binds[:3]}"
        )
    print(
        f"AOT symbols verified strong and locally bound: {strong_definitions} strong definitions; "
        f"0 weak definitions/references/dyld weak lookups"
    )
    return aot_symbols, strong_definitions, len(weak_dynamic_binds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    parse_macho(args.binary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
