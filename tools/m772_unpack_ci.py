#!/usr/bin/env python3
"""Verify and unpack the owner-provided PS3Recomp lift bundle for M7.72 CI."""
import argparse
import hashlib
import json
import pathlib
import zipfile

PARTS = [
    ("AscensionRecomp-PS3Recomp-Lift.zip.part00", "5c150c6557cf639ccd583fd351e3425ac67781fb142ab7edec713e5a15a2158a"),
    ("AscensionRecomp-PS3Recomp-Lift.zip.part01", "f82ac92b11b542be41720d129377b6655586293be9d3d6ee05d382fdde317167"),
    ("AscensionRecomp-PS3Recomp-Lift.zip.part02", "36a922021e51140983bd057cb0320f685b2f530be05f0d11f0291384a5b4129e"),
]
ZIP_SHA256 = "0ff6e0a8ae608c23a5b66400813681c563b002d008f273feac324e4013e5865e"
ZIP_BYTES = 243404277
ROOT_NAME = "AscensionRecomp-PS3Recomp-Lift"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--upstream", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / "lift.zip"
    with archive.open("wb") as dest:
        for name, expected in PARTS:
            part = args.parts / name
            if sha256(part) != expected:
                raise SystemExit(f"M7.72 source shard SHA-256 mismatch: {name}")
            with part.open("rb") as src:
                for block in iter(lambda: src.read(8 << 20), b""):
                    dest.write(block)
    if archive.stat().st_size != ZIP_BYTES or sha256(archive) != ZIP_SHA256:
        raise SystemExit("M7.72 source archive size/SHA-256 mismatch")

    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != 680 or len(set(names)) != len(names):
            raise SystemExit("M7.72 source ZIP inventory count mismatch")
        root = pathlib.PurePosixPath(ROOT_NAME)
        for name in names:
            path = pathlib.PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != ROOT_NAME:
                raise SystemExit(f"unsafe M7.72 source path: {name}")
            if name.lower().endswith((".elf", ".self", ".sprx", ".rap", ".pkg")):
                raise SystemExit(f"original game executable/content must not be staged: {name}")
        if bundle.testzip() is not None:
            raise SystemExit("M7.72 source ZIP CRC failed")
        bundle.extractall(args.output)

    source = args.output / ROOT_NAME
    ppu = sorted(source.joinpath("ppu").glob("ppu_recomp_*.cpp"))
    spu = sorted(source.joinpath("spu").glob("*/spu_recomp.c"))
    table = source / "ppu" / "ppu_recomp_table.cpp"
    if len(ppu) != 651 or not table.is_file() or len(spu) != 4:
        raise SystemExit(f"M7.72 source inventory mismatch: PPU={len(ppu)} SPU={len(spu)}")
    text = table.read_text(errors="replace")
    if "function_table_count = 29849" not in text or "func_0052A740" not in text or "func_0052E3F4" not in text:
        raise SystemExit("M7.72 PPU frontier/table checks failed")
    (source / "runtime").symlink_to((args.upstream / "runtime").resolve())
    result = {
        "schema": "ascension-m772-source-preflight-v1",
        "zip_sha256": ZIP_SHA256,
        "zip_bytes": ZIP_BYTES,
        "ppu_translation_units_including_table": len(ppu),
        "ppu_function_table_entries": 29849,
        "frontier_0052a740_present": True,
        "frontier_callee_0052e3f4_present": True,
        "spu_translation_units": len(spu),
        "original_elf_in_repo": False,
        "ios_compiled": False,
        "ipa_linked": False,
        "device_executed": "NOT_MEASURED",
    }
    (args.output / "m772-source-preflight.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
