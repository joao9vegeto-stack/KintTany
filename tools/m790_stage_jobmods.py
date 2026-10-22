#!/usr/bin/env python3
"""Verify and stage the checked-in native NPUA WWS job-module sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath


EXPECTED = {
    "schema": "ascension-m790-generated-wws-source-sha256-v1",
    "generator": "tools/m790_prepare_jobmods.py",
    "gowa_pc_commit": "45840d709a4e48a1d12d0803e323ba5c8568ab2a",
    "ps3recomp_commit": "f6ab60baf37662bd712592b7ef9f66891972a5fc",
    "source_title": "UP9000-NPUA80918",
    "modules": 31,
    "lifted_functions": 20418,
    "unsupported_executable_words": 0,
}
RAW_SUFFIXES = {".bin", ".elf", ".self", ".rap", ".zip", ".ips"}


def verify_source(root: Path) -> tuple[int, int]:
    checksums_path = root / "sources.sha256.json"
    checksums = json.loads(checksums_path.read_text())
    for key, value in EXPECTED.items():
        if checksums.get(key) != value:
            raise SystemExit(f"generated WWS source attestation mismatch: {key}")

    listed: dict[str, dict] = {}
    for item in checksums.get("files", []):
        rel = PurePosixPath(item.get("path", ""))
        if not rel.parts or rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe generated-source path in SHA manifest: {rel}")
        key = rel.as_posix()
        if key in listed or key == "sources.sha256.json":
            raise SystemExit(f"duplicate or recursive generated-source path: {key}")
        listed[key] = item
        path = root.joinpath(*rel.parts)
        if not path.is_file() or path.stat().st_size != item.get("size"):
            raise SystemExit(f"generated WWS source is missing or has wrong size: {key}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item.get("sha256"):
            raise SystemExit(f"generated WWS source SHA-256 mismatch: {key}")

    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(listed) | {"sources.sha256.json"}:
        missing = sorted(actual - set(listed) - {"sources.sha256.json"})
        absent = sorted(set(listed) - actual)
        raise SystemExit(f"generated WWS source file set changed: extra={missing}, missing={absent}")
    if any(Path(name).suffix.lower() in RAW_SUFFIXES for name in actual):
        raise SystemExit("raw game, SELF, license, or SPU module found in staged source tree")

    manifest = json.loads((root / "jobmods_manifest.json").read_text())
    attestation = json.loads((root / "jobmods_attestation.json").read_text())
    names = {item["name"] for item in manifest}
    if (len(manifest) != EXPECTED["modules"] or
            len(names) != EXPECTED["modules"] or
            sum(int(item["funcs"]) for item in manifest) != EXPECTED["lifted_functions"] or
            any(int(item["unsupported"]) for item in manifest) or
            any(not (root / name / "spu_recomp.c").is_file() or
                not (root / name / "spu_recomp.h").is_file() for name in names)):
        raise SystemExit("generated WWS module manifest does not match its C sources")
    if (attestation.get("schema") != "ascension-m790-elf-jobmods-v1" or
            attestation.get("source_title") != EXPECTED["source_title"] or
            attestation.get("source_elf_structurally_matches_self") is not True or
            attestation.get("modules") != EXPECTED["modules"] or
            attestation.get("lifted_functions") != EXPECTED["lifted_functions"] or
            attestation.get("unclassified_words") != 0 or
            attestation.get("registered_overlay_image_ids") != [200, 230] or
            attestation.get("license_extracted") is not False):
        raise SystemExit("generated WWS module attestation is incomplete")
    registry = (root / "jobmods_register.c").read_text()
    if ("ascension_npua_jobmods_register_all" not in registry or
            "__attribute__((constructor))" in registry):
        raise SystemExit("generated WWS registration source is missing or unsafe")
    return len(manifest), EXPECTED["lifted_functions"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    modules, functions = verify_source(args.source.resolve())
    out = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(args.source.resolve(), out)
    verify_source(out)
    print(f"Staged {modules} native NPUA WWS modules; functions={functions}; unresolved=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
