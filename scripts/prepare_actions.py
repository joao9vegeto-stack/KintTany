#!/usr/bin/env python3
"""Download only the Colab-prepared Route C workspace and external BOTW game data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath


TITLE_ID = "01007EF00011E000"
PACKAGE_VERSION = "v1114112"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"


def fail(message: str) -> None:
    raise SystemExit("[Link2iOS] ERROR: " + message)


def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    digest = hashlib.sha256()
    total = 0
    with temp.open("wb") as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=64 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"Drive: {item.get('name', item['id'])} {status.progress() * 100:.1f}%", flush=True)
    with temp.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
            total += len(block)
    if total != int(item["size"]):
        temp.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item.get('name', item['id'])}: expected {item['size']}, got {total}")
    if digest.hexdigest().lower() != str(item["sha256"]).lower():
        temp.unlink(missing_ok=True)
        fail(f"Drive SHA-256 mismatch for {item.get('name', item['id'])}")
    temp.replace(destination)


def extract_verified_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
    if proc.stdout is None:
        fail("could not start zstd decompression.")
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                rel = PurePosixPath(member.name)
                if rel.is_absolute() or ".." in rel.parts:
                    fail(f"unsafe archive path: {member.name}")
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    fail(f"unsupported archive entry: {member.name}")
                target = destination.joinpath(*[part for part in rel.parts if part not in ("", ".")])
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    fail(f"cannot read archive member: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
    finally:
        proc.stdout.close()
    if proc.wait() != 0:
        fail("zstd decompression failed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    if handoff.get("project") != "Link2iOS" or handoff.get("branch") != "Link2iOS":
        fail("handoff branch/project mismatch.")
    if handoff.get("title_id") != TITLE_ID or handoff.get("package_version") != PACKAGE_VERSION:
        fail("handoff is not BOTW 1.9.0 / v1114112.")
    if handoff.get("nx2apple_tag") != NX2APPLE_TAG or handoff.get("engine_pin") != ENGINE_PIN:
        fail("NX2Apple/NXNative pin mismatch in handoff.")
    if not handoff.get("request_id"):
        fail("handoff request_id is missing.")

    prepared_manifest = handoff.get("prepared") or {}
    if prepared_manifest.get("shader_package_key") is None:
        fail("Colab did not hand off the NVN shader-package content key.")
    if prepared_manifest.get("shader_chain") is None:
        fail("Colab did not hand off the NVN shader chain.")
    if prepared_manifest.get("engine_pin") != ENGINE_PIN:
        fail("Colab preparation manifest carries another NXNative pin.")

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        fail("GitHub Actions secret GOOGLE_SERVICE_ACCOUNT_JSON is empty.")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    api = build("drive", "v3", credentials=credentials, cache_discovery=False)

    root = args.destination.resolve()
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    work_archive = root / "botw-work.tar.zst"
    print("[Link2iOS] Downloading the Colab-prepared workspace (no NSP or prod.keys)...")
    download_drive_file(api, handoff["work_archive"], work_archive)

    work = root / "work"
    print("[Link2iOS] Verifying and extracting prepared Linux artifacts...")
    extract_verified_archive(work_archive, work)
    work_archive.unlink()

    prep_path = work / "link2ios-linux-prep.json"
    if not prep_path.is_file():
        fail("Colab Linux preparation manifest is missing from the workspace.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    for key in ("project", "title_id", "package_version", "nx2apple_tag", "engine_pin",
                "shader_package_key", "shader_chain", "romfs_relative_path", "romfs_id_relative_path"):
        if prep.get(key) != prepared_manifest.get(key):
            fail(f"handoff and workspace disagree on {key}.")
    if prep.get("project") != "Link2iOS" or prep.get("title_id") != TITLE_ID:
        fail("prepared workspace is not the BOTW Link2iOS workspace.")
    if prep.get("package_version") != PACKAGE_VERSION or prep.get("engine_pin") != ENGINE_PIN:
        fail("prepared workspace package version or engine pin is incorrect.")

    romfs_rel = PurePosixPath(prep["romfs_relative_path"])
    romfs_id_rel = PurePosixPath(prep["romfs_id_relative_path"])
    if romfs_rel.is_absolute() or ".." in romfs_rel.parts or romfs_id_rel.is_absolute() or ".." in romfs_id_rel.parts:
        fail("invalid RomFS path in Colab manifest.")
    romfs_path = work.joinpath(*romfs_rel.parts)
    romfs_id_path = work.joinpath(*romfs_id_rel.parts)
    game_data = handoff.get("game_data") or {}
    expected_aoc = {"1.img", "2.img"}
    handoff_aoc = game_data.get("aoc", [])
    manifest_aoc = prep.get("aoc_images", [])
    if {Path(item.get("name", "")).name for item in handoff_aoc} != expected_aoc:
        fail("Drive handoff must contain both BOTW AOC images 1.img and 2.img.")
    if {Path(item.get("name", "")).name for item in manifest_aoc} != expected_aoc:
        fail("Colab workspace manifest must record both BOTW AOC images 1.img and 2.img.")
    if prep.get("aoc_title_ids") != {
        "1.img": "01007EF00011F001",
        "2.img": "01007EF00011F002",
    }:
        fail("Colab manifest AOC title IDs do not match BOTW DLC Pack 1 and Pack 2.")
    if game_data.get("romfs_relative_path") != prep["romfs_relative_path"]:
        fail("Drive handoff RomFS path differs from Colab preparation.")
    if not romfs_id_path.is_file():
        fail("NX2Apple RomFS identity sidecar was not retained in the Colab workspace.")

    print("[Link2iOS] Restoring only RomFS and DLC AOC from Drive...")
    download_drive_file(api, game_data["romfs"], romfs_path)
    aoc_dir = work / "aoc"
    aoc_dir.mkdir(parents=True, exist_ok=True)
    for item in game_data.get("aoc", []):
        filename = Path(item["name"]).name
        if not filename.lower().endswith(".img"):
            fail(f"unexpected AOC image name: {filename}")
        download_drive_file(api, item, aoc_dir / filename)
    restored_aoc = sorted(aoc_dir.glob("*.img"))
    if {path.name for path in restored_aoc} != expected_aoc:
        fail("restored AOC files are not exactly 1.img and 2.img.")
    if len(restored_aoc) != len(game_data.get("aoc", [])):
        fail("restored AOC count does not match the Drive handoff.")
    if len(restored_aoc) != len(prep.get("aoc_images", [])):
        fail("restored AOC count does not match the Colab workspace manifest.")
    if not romfs_path.is_file() or not romfs_path.stat().st_size:
        fail("external BOTW RomFS image was not restored.")

    prepared = {
        "project": "Link2iOS",
        "title_id": TITLE_ID,
        "package_version": PACKAGE_VERSION,
        "nx2apple_tag": NX2APPLE_TAG,
        "engine_pin": ENGINE_PIN,
        "request_id": handoff["request_id"],
        "work_dir": str(work),
        "romfs_path": str(romfs_path),
        "romfs_id_path": str(romfs_id_path),
        "aoc_dir": str(aoc_dir),
        "aoc_count": len(restored_aoc),
        "aoc_images": sorted(path.name for path in restored_aoc),
        "modules": prep["modules"],
        "romfs_relative_path": prep["romfs_relative_path"],
        "romfs_id_relative_path": prep["romfs_id_relative_path"],
        "shader_package_key": prep["shader_package_key"],
        "shader_chain": prep["shader_chain"],
        "game_data": game_data,
    }
    prepared_path = root / "actions-input.json"
    prepared_path.write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(prepared, indent=2))
    print("[Link2iOS] Complete: Actions has workspace + RomFS/AOC only; original NSPs and prod.keys never left Colab.")


if __name__ == "__main__":
    main()
