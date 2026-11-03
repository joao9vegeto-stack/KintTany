#!/usr/bin/env python3
"""Stage the original PS4 dump in the exact directory layout expected upstream."""
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

def copy_canonical(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    if not target.is_file() or target.stat().st_size != source.stat().st_size:
        raise ValueError(f"Falha ao posicionar {source.name} em {target}")
    if digest(source) != digest(target):
        raise ValueError(f"SHA-256 diverge após posicionar {source.name}")
    return target

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

    param_source = unique_file(game, "param.sfo")
    if not param_source.read_bytes().startswith(b"\0PSF"):
        raise ValueError("param.sfo sem magic PSF")
    param_target = copy_canonical(param_source, game / "sce_sys" / "param.sfo")

    # gow3-macos-arm64/scripts/prepare.py and link_modules.py open these exact paths.
    module_records = []
    for name in ("libc.prx", "libSceFios2.prx"):
        source = unique_file(game, name)
        target = copy_canonical(source, game / "sce_module" / name)
        module_records.append({
            "name": name, "source_path": str(source.relative_to(output)),
            "canonical_path": str(target.relative_to(output)),
            **validate_self(target),
        })

    eboot_target = copy_canonical(eboot, game / "eboot.bin")
    eboot_record = validate_self(eboot_target)

    # Fail here, not deep in upstream code, if its required module/resource layout is absent.
    required = [game / "sce_module" / "libc.prx",
                game / "sce_module" / "libSceFios2.prx",
                game / "sce_sys" / "param.sfo",
                game / "dvdroot_ps4"]
    missing = [str(p.relative_to(output)) for p in required if not p.exists()]
    if missing:
        raise ValueError("Estrutura requerida pelo preparador upstream ausente: " + ", ".join(missing))

    manifest = {
        "eboot": {"path": "game/eboot.bin", **eboot_record},
        "assets_zip": {"path": str(archive), "bytes": archive.stat().st_size, "sha256": digest(archive)},
        "validated_modules": module_records,
        "param_sfo": str(param_target.relative_to(output)),
        "required_paths_verified": [str(p.relative_to(output)) for p in required],
        "staging_policy": "Original SELF bytes preserved; modules copied to exact upstream sce_module paths and SHA-256 verified.",
    }
    (output / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"prepare_dump: {error}")
