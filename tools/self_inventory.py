#!/usr/bin/env python3
"""Read-only PS3 SCE SELF metadata inspector. No decryption, keys or game bytes exported."""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

class SelfInventoryError(ValueError):
    pass

def _bounded(start, length, limit, name):
    if start < 0 or length < 0 or start > limit or length > limit - start:
        raise SelfInventoryError(name + " fora dos limites")

def inspect(path: Path) -> dict:
    data = path.read_bytes()
    limit = len(data)
    _bounded(0, 0x70, limit, "SCE header")
    magic, version, revision, kind, metadata_off, header_size, elf_size = struct.unpack_from(">IIHHIQQ", data, 0)
    if magic != 0x53434500 or version != 2 or kind != 1:
        raise SelfInventoryError("nao e PS3 SCE SELF v2")
    ext, app, elf_off, phdr, shdr, seginfo, scever, ctrl, ctrl_size = struct.unpack_from(">9Q", data, 0x20)
    _bounded(app, 32, limit, "appinfo")
    _bounded(elf_off, 64, limit, "ELF header")
    authority, vendor, ptype, pversion, _pad = struct.unpack_from(">QIIQQ", data, app)
    ident, etype, machine, ev, entry, ephoff, eshoff, flags, ehsz, psz, count, ssz, scount, sindex = struct.unpack_from(">16sHHIQQQIHHHHHH", data, elf_off)
    if ident[:7] != b"\x7fELF\x02\x02\x01" or machine != 21 or ev != 1:
        raise SelfInventoryError("ELF interno nao e PPU PowerPC64 big-endian")
    if count > 4096 or psz < 56:
        raise SelfInventoryError("program headers invalidos")
    _bounded(phdr, count * psz, limit, "program header table")
    _bounded(seginfo, count * 32, limit, "segment info table")
    _bounded(ctrl, ctrl_size, limit, "supplemental headers")
    segments = []
    for index in range(count):
        typ, pflags, poff, vaddr, pa, filesz, memsz, align = struct.unpack_from(">IIQQQQQQ", data, phdr + index * psz)
        stored_off, stored_size, compression, unk, encryption = struct.unpack_from(">QQIIQ", data, seginfo + index * 32)
        if stored_size:
            _bounded(stored_off, stored_size, limit, "stored segment " + str(index))
        segments.append({
            "index": index, "type": "0x%x" % typ, "flags": "0x%x" % pflags,
            "elf_offset": poff, "vaddr": "0x%x" % vaddr,
            "elf_filesz": filesz, "elf_memsz": memsz,
            "stored_offset": stored_off, "stored_size": stored_size,
            "compression": {1: "plain", 2: "zlib"}.get(compression, "unknown"),
            "encryption": {0: "unrequested", 1: "completed", 2: "requested"}.get(encryption, "unknown"),
        })
    supplementals = []
    npdrm = None
    cursor = ctrl
    end = ctrl + ctrl_size
    for _ in range(32):
        if cursor >= end:
            break
        _bounded(cursor, 16, end, "supplemental header")
        stype, size, next_ = struct.unpack_from(">IIQ", data, cursor)
        if size < 16:
            raise SelfInventoryError("supplemental header tamanho invalido")
        _bounded(cursor, size, end, "supplemental header")
        supplementals.append({"type": stype, "size": size})
        if stype == 3 and size >= 0x90:
            npd = cursor + 16
            if data[npd:npd + 4] == b"NPD\x00":
                v, license_type, app_type = struct.unpack_from(">III", data, npd + 4)
                cid = data[npd + 16:npd + 64].split(b"\x00", 1)[0].decode("ascii")
                npdrm = {
                    "version": v, "license_type": license_type, "app_type": app_type,
                    "content_id": cid,
                    "license_label": {1: "network", 2: "local", 3: "free"}.get(license_type, "unknown"),
                }
        cursor += size
        if not next_:
            break
    return {
        "schema": "ascension-recomp/self-inventory-v1", "filename": path.name,
        "file_size_bytes": limit, "sha256": hashlib.sha256(data).hexdigest(),
        "sce": {
            "key_revision": "0x%04x" % revision, "program_type": ptype,
            "program_sceversion": "0x%x" % pversion,
            "retail_encrypted": revision != 0x8000,
            "metadata_offset": metadata_off, "header_size": header_size,
            "elf_declared_size": elf_size,
        },
        "elf": {
            "architecture": "PPU PowerPC64", "endianness": "big",
            "entry": "0x%x" % entry, "program_header_count": count,
            "section_header_count": scount, "segments": segments,
        },
        "npdrm": npdrm, "supplemental_headers": supplementals,
        "decryption_performed": False,
        "next_gate": "A genuine decrypted ELF is required by ppu_loader.py; embedded ELF header is insufficient",
    }

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("self_file", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    try:
        report = inspect(args.self_file)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("OK", report["filename"], report["elf"]["architecture"], report["npdrm"])
        return 0
    except (ValueError, OSError, struct.error) as ex:
        ap.exit(2, "ERROR: %s\n" % ex)

if __name__ == "__main__":
    raise SystemExit(main())
