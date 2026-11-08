#!/usr/bin/env python3
"""Remove only the bundled RomFS image from a compiled NXNative iOS IPA.

The output is a thin IPA plus a separate DMROMFS1 romfs.img for:
    Files -> On My iPhone -> <app> -> romfs.img

The app executable, rewritten game modules, profile, shader maps and Metal
libraries remain inside the IPA. This tool does not compile games or decrypt
NSP/XCI dumps.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

ROMFS_MAGIC = b"DMROMFS1"
ROMFS_HEADER = struct.Struct("<8sQQQ")
ROMFS_ENTRY_SIZE = 24
CHUNK = 8 * 1024 * 1024


class ThinIPAError(RuntimeError):
    pass


def validate_romfs_header(path: Path) -> tuple[int, int, int]:
    size_on_disk = path.stat().st_size
    if size_on_disk < ROMFS_HEADER.size:
        raise ThinIPAError(f"RomFS image is truncated: {path}")
    with path.open("rb") as stream:
        raw = stream.read(ROMFS_HEADER.size)
    magic, index_offset, index_size, count = ROMFS_HEADER.unpack(raw)
    if magic != ROMFS_MAGIC:
        raise ThinIPAError("romfs.img does not have the DMROMFS1 signature.")
    if (
        count <= 0
        or index_offset < ROMFS_HEADER.size
        or index_offset > size_on_disk
        or index_size != size_on_disk - index_offset
        or count > index_size // ROMFS_ENTRY_SIZE
    ):
        raise ThinIPAError("romfs.img has an invalid or incomplete DMROMFS1 index.")
    return index_offset, index_size, count


def _find_app_and_romfs(names: list[str]) -> tuple[str, str, str]:
    info_paths = [
        name for name in names
        if len(name.split("/")) == 3
        and name.split("/")[0] == "Payload"
        and name.split("/")[1].endswith(".app")
        and name.split("/")[2] == "Info.plist"
    ]
    if len(info_paths) != 1:
        raise ThinIPAError(
            f"Expected one Payload/<name>.app/Info.plist; found {len(info_paths)}."
        )
    info_path = info_paths[0]
    app_root = "/".join(info_path.split("/")[:2])
    romfs_paths = [
        name for name in names
        if name.lower() == f"{app_root}/romfs.img".lower()
    ]
    if len(romfs_paths) != 1:
        raise ThinIPAError(
            f"Expected one {app_root}/romfs.img inside the IPA; found {len(romfs_paths)}."
        )
    return app_root, info_path, romfs_paths[0]


def split_ipa(source_ipa: Path, thin_ipa: Path, romfs_out: Path, *, force: bool = False) -> tuple[int, int]:
    source_ipa = source_ipa.resolve()
    thin_ipa = thin_ipa.resolve()
    romfs_out = romfs_out.resolve()

    if not source_ipa.is_file():
        raise ThinIPAError(f"Input IPA does not exist: {source_ipa}")
    if len({source_ipa, thin_ipa, romfs_out}) != 3:
        raise ThinIPAError("Input IPA, thin IPA and RomFS output must be different files.")
    if not force and (thin_ipa.exists() or romfs_out.exists()):
        raise ThinIPAError("An output file already exists. Use --force to replace it.")

    thin_ipa.parent.mkdir(parents=True, exist_ok=True)
    romfs_out.parent.mkdir(parents=True, exist_ok=True)
    thin_tmp = thin_ipa.with_name(thin_ipa.name + ".partial")
    romfs_tmp = romfs_out.with_name(romfs_out.name + ".partial")
    for temp_path in (thin_tmp, romfs_tmp):
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass

    try:
        with zipfile.ZipFile(source_ipa, "r", allowZip64=True) as zin:
            names = [item.filename for item in zin.infolist()]
            app_root, info_path, romfs_member = _find_app_and_romfs(names)

            try:
                with zin.open(info_path, "r") as stream:
                    info = plistlib.loads(stream.read())
            except (KeyError, plistlib.InvalidFileException, ValueError) as exc:
                raise ThinIPAError(f"Unable to read {info_path}: {exc}") from exc

            executable = info.get("CFBundleExecutable")
            if not isinstance(executable, str) or not executable.strip():
                raise ThinIPAError("Info.plist does not name CFBundleExecutable.")
            executable_path = f"{app_root}/{executable}"
            if executable_path not in names:
                raise ThinIPAError(f"The app executable is missing: {executable_path}")

            romfs_info = next(item for item in zin.infolist() if item.filename == romfs_member)
            with zin.open(romfs_info, "r") as src, romfs_tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=CHUNK)
            validate_romfs_header(romfs_tmp)

            with zipfile.ZipFile(thin_tmp, "w", allowZip64=True) as zout:
                zout.comment = zin.comment
                for item in zin.infolist():
                    if item.filename == romfs_member:
                        continue
                    if item.is_dir():
                        zout.writestr(item, b"")
                        continue
                    with zin.open(item, "r") as src, zout.open(item, "w", force_zip64=True) as dst:
                        shutil.copyfileobj(src, dst, length=CHUNK)

        # Re-open and verify the final IPA directory structure without reading every
        # potentially multi-gigabyte shader or executable member into memory.
        with zipfile.ZipFile(thin_tmp, "r", allowZip64=True) as check:
            final_names = [item.filename for item in check.infolist()]
            if romfs_member in final_names:
                raise ThinIPAError("RomFS was not removed from the thin IPA.")
            if info_path not in final_names or executable_path not in final_names:
                raise ThinIPAError("The thin IPA lost its app metadata or executable.")
            if not any(name.startswith(app_root + "/msl/") for name in final_names):
                raise ThinIPAError("The IPA has no bundled iOS Metal shader libraries.")
        if thin_tmp.stat().st_size >= source_ipa.stat().st_size:
            raise ThinIPAError("The resulting IPA is not smaller than the input IPA.")

        os.replace(romfs_tmp, romfs_out)
        os.replace(thin_tmp, thin_ipa)
        romfs_bytes = romfs_out.stat().st_size
        thin_bytes = thin_ipa.stat().st_size
        return thin_bytes, romfs_bytes
    finally:
        for temp_path in (thin_tmp, romfs_tmp):
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="aida-thin-ipa-") as temp:
        root = Path(temp)
        full = root / "full.ipa"
        thin = root / "thin.ipa"
        romfs = root / "romfs.img"
        app = "Payload/TestGame.app"
        image = ROMFS_MAGIC + struct.pack("<QQQ", ROMFS_HEADER.size, ROMFS_ENTRY_SIZE, 1) + (b"\0" * ROMFS_ENTRY_SIZE)
        info = plistlib.dumps({"CFBundleExecutable": "TestGame"}, fmt=plistlib.FMT_BINARY)

        with zipfile.ZipFile(full, "w", allowZip64=True) as archive:
            archive.writestr(f"{app}/Info.plist", info, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr(f"{app}/TestGame", b"fake-arm64-executable", compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr(f"{app}/msl/b-test/test.metallib", b"shader-library", compress_type=zipfile.ZIP_STORED)
            archive.writestr(f"{app}/romfs.img", image, compress_type=zipfile.ZIP_STORED)

        thin_size, data_size = split_ipa(full, thin, romfs)
        if thin_size >= full.stat().st_size or data_size != len(image):
            raise ThinIPAError("Self-test failed: output sizes are incorrect.")
        if romfs.read_bytes() != image:
            raise ThinIPAError("Self-test failed: external RomFS image changed.")
        with zipfile.ZipFile(thin, "r") as archive:
            members = archive.namelist()
            if f"{app}/romfs.img" in members:
                raise ThinIPAError("Self-test failed: RomFS still appears in IPA.")
            if f"{app}/TestGame" not in members or f"{app}/msl/b-test/test.metallib" not in members:
                raise ThinIPAError("Self-test failed: app executable or shaders were lost.")
    print("PASS: thin IPA retains app/executable/Metal shaders; DMROMFS1 image is separate.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_ipa", nargs="?", type=Path, help="full IPA produced by NXNativeWindows")
    parser.add_argument("thin_ipa", nargs="?", type=Path, help="output thin IPA")
    parser.add_argument("romfs_out", nargs="?", type=Path, help="external romfs.img output")
    parser.add_argument("--force", action="store_true", help="replace existing output files")
    parser.add_argument("--self-test", action="store_true", help="run a synthetic packaging test")
    args = parser.parse_args(argv)

    try:
        if args.self_test:
            self_test()
            return 0
        if not (args.source_ipa and args.thin_ipa and args.romfs_out):
            parser.error("source_ipa, thin_ipa and romfs_out are required unless --self-test is used")
        thin_size, romfs_size = split_ipa(args.source_ipa, args.thin_ipa, args.romfs_out, force=args.force)
        print(f"Thin IPA: {args.thin_ipa} ({thin_size / (1024**3):.2f} GiB)")
        print(f"RomFS:    {args.romfs_out} ({romfs_size / (1024**3):.2f} GiB)")
        return 0
    except (OSError, zipfile.BadZipFile, ThinIPAError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
