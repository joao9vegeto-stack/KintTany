#!/usr/bin/env python3
"""Private, read-only ELF structure inventory (PS3 PPU / SPU). No decryption or game data export."""
from __future__ import annotations
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys

MACHINES = {21: "PPU PowerPC64", 23: "SPU"}
class ELFError(ValueError):
    pass

def inspect_elf(path: Path) -> dict:
    if not path.is_file():
        raise ELFError("arquivo nao encontrado: " + str(path))
    size = path.stat().st_size
    if size < 52:
        raise ELFError("muito pequeno para cabecalho ELF")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[:4] != b"\x7fELF":
            raise ELFError("nao e ELF descriptografado (SELF/EBOOT.BIN criptografado nao serve)")
        cls, endian, version = data[4], data[5], data[6]
        if cls not in (1, 2) or endian != 2 or version != 1:
            raise ELFError("requer ELF32/ELF64 big-endian PS3")
        if cls == 2:
            if size < 64:
                raise ELFError("cabecalho ELF64 truncado")
            fields = struct.unpack_from(">HHIQQQIHHHHHH", data, 16)
            ph_format, min_ph_size, bits = ">IIQQQQQQ", 56, 64
        else:
            fields = struct.unpack_from(">HHIIIIIHHHHHH", data, 16)
            ph_format, min_ph_size, bits = ">IIIIIIII", 32, 32
        etype, machine, eversion, entry, phoff, shoff, flags, ehsize, phentsize, phnum, shentsize, shnum, shstrndx = fields
        if machine not in MACHINES:
            raise ELFError("arquitetura inesperada e_machine=" + str(machine))
        if machine == 21 and bits != 64:
            raise ELFError("PPU exige ELF64")
        if machine == 23 and bits != 32:
            raise ELFError("SPU exige ELF32")
        if eversion != 1 or ehsize < (64 if bits == 64 else 52):
            raise ELFError("versao/cabecalho ELF invalidos")
        if phnum == 0xffff:
            raise ELFError("contagem estendida de program headers ainda nao implementada")
        if phnum > 4096:
            raise ELFError("numero excessivo de program headers")
        if phnum and (phentsize < min_ph_size or phoff > size or phnum * phentsize > size - phoff):
            raise ELFError("program headers fora dos limites do arquivo")
        segments = []
        for i in range(phnum):
            row = struct.unpack_from(ph_format, data, phoff + i * phentsize)
            if bits == 64:
                ptype, pflags, offset, vaddr, paddr, filesz, memsz, align = row
            else:
                ptype, offset, vaddr, paddr, filesz, memsz, pflags, align = row
            if ptype != 1:
                continue
            if offset > size or filesz > size - offset:
                raise ELFError("segmento PT_LOAD " + str(i) + " fora dos limites")
            if filesz > memsz:
                raise ELFError("segmento PT_LOAD " + str(i) + ": filesz > memsz")
            segments.append({
                "index": i, "offset": offset, "vaddr": "0x%x" % vaddr,
                "filesz": filesz, "memsz": memsz,
                "permissions": "".join(c if pflags & m else "-" for c, m in (("R",4),("W",2),("X",1))),
                "alignment": align
            })
        return {
            "file": path.name,
            "sha256": digest.hexdigest(),
            "size_bytes": size,
            "elf_class": bits,
            "endianness": "big",
            "machine": MACHINES[machine],
            "e_machine": machine,
            "e_type": etype,
            "entry": "0x%x" % entry,
            "program_headers": phnum,
            "load_segments": segments,
            "section_headers": shnum,
            "warnings": [] if segments else ["nenhum segmento PT_LOAD; verificar arquivo"]
        }

def main(argv=None):
    parser = argparse.ArgumentParser(description="Inventario local PS3 ELF sem extrair codigo; nao aceita EBOOT.BIN SELF.")
    parser.add_argument("--elf", required=True, type=Path, help="EBOOT.ELF descriptografado da sua copia")
    parser.add_argument("--spu", type=Path, action="append", default=[], help="SPU ELF separado (repetir)")
    parser.add_argument("--out", required=True, type=Path, help="JSON de diagnostico; nao e o jogo")
    args = parser.parse_args(argv)
    try:
        payload = {
            "schema": "ascension-recomp/inventory-v1",
            "note": "metadata only, no executable bytes",
            "ppu": inspect_elf(args.elf),
            "spu_modules": [inspect_elf(f) for f in args.spu]
        }
        if payload["ppu"]["e_machine"] != 21:
            raise ELFError("--elf deve apontar ao executavel PPU PowerPC64")
        for item in payload["spu_modules"]:
            if item["e_machine"] != 23:
                raise ELFError("--spu deve apontar a ELF32 SPU")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("OK PPU:", payload["ppu"]["machine"], payload["ppu"]["size_bytes"], "bytes; PT_LOAD:", len(payload["ppu"]["load_segments"]))
        print("OK SPU:", len(payload["spu_modules"]), "arquivo(s)")
        print("Manifest local:", args.out)
        return 0
    except (OSError, ELFError, struct.error, ValueError) as err:
        print("ERRO:", err, file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
