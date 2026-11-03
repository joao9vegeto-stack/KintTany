#!/usr/bin/env python3
"""Stage the original PS4 dump for the pinned upstream AOT preparer.

Do not rewrite SELF containers here. The upstream parser consumes the original
SELF entry flags and segment indices; replacing them with a guessed ELF breaks
its loader and loses the original module metadata.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import struct
import zipfile
from pathlib import Path

SELF_MAGIC = b"\x4f\x15\x3d\x1d"

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        target = (destination / name).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"ZIP path traversal: {info.filename}")
        if info.flag_bits & 1:
            raise ValueError(f"ZIP entry encrypted: {info.filename}")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)

def unique_file(root: Path, basename: str) -> Path:
    matches = [p for p in root.rglob("*") if p.is_file() and p.name.lower() == basename.lower()]
    if len(matches) != 1:
        raise ValueError(f"Esperado exatamente um {basename}; encontrados: {len(matches)}")
    return matches[0]

def validate_self(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 0x20 or data[:4] != SELF_MAGIC:
        raise ValueError(f"{path.name}: esperado SELF PS4 original; magic={data[:16].hex()} bytes={len(data)}")
    count = struct.unpack_from("<H", data, 24)[0]
    table_end = 0x20 + count * 0x20
    if not 0 < count <= 1024 or table_end > len(data):
        raise ValueError(f"{path.name}: tabela SELF inválida (entries={count}, bytes={len(data)})")
    entries = []
    for index in range(count):
        props, offset, stored, unpacked = struct.unpack_from("<QQQQ", data, 0x20 + index * 0x20)
        if offset > len(data) or stored > len(data) - offset:
            raise ValueError(f"{path.name}: entrada SELF {index} fora do arquivo")
        entries.append({
            "index": index, "properties": f"0x{props:016x}",
            "offset": offset, "stored_size": stored, "unpacked_size": unpacked,
            "encrypted": bool(props & (1 << 1)), "compressed": bool(props & (1 << 3)),
            "segment_index": (props >> 20) & 0xfff,
            "has_segment_payload": bool(props & 0x800),
        })
    return {
        "format": "original PS4 SELF (preserved byte-for-byte)",
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "entry_count": count, "entries": entries,
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eboot", required=True)
    parser.add_argument("--assets-zip", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    eboot, archive, output = Path(args.eboot), Path(args.assets_zip), Path(args.out)
    if not eboot.is_file() or not archive.is_file():
        raise SystemExit("eboot.bin ou G3.zip ausente")
    if output.exists():
        shutil.rmtree(output)
    game = output / "game"
    game.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zf:
        safe_extract(zf, game)

    param = unique_file(game, "param.sfo")
    if not param.read_bytes().startswith(b"\0PSF"):
        raise ValueError("param.sfo sem magic PSF")
    sfo_target = game / "sce_sys" / "param.sfo"
    sfo_target.parent.mkdir(parents=True, exist_ok=True)
    if param.resolve() != sfo_target.resolve():
        shutil.copy2(param, sfo_target)

    module_records = []
    for name in ("libc.prx", "libSceFios2.prx"):
        module = unique_file(game, name)
        module_records.append({
            "name": name, "path": str(module.relative_to(output)),
            **validate_self(module),
        })

    eboot_target = game / "eboot.bin"
    shutil.copy2(eboot, eboot_target)
    eboot_record = validate_self(eboot_target)
    manifest = {
        "eboot": {"path": "game/eboot.bin", **eboot_record},
        "assets_zip": {"path": str(archive), "bytes": archive.stat().st_size, "sha256": digest(archive)},
        "validated_modules": module_records,
        "param_sfo": "game/sce_sys/param.sfo",
        "staging_policy": "Original SELF files preserved byte-for-byte; upstream prepare.py owns SELF parsing and ELF reconstruction.",
    }
    (output / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"prepare_dump: {error}")
