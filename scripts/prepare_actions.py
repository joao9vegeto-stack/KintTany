#!/usr/bin/env python3
"""Download and verify the Colab handoff, then restore split BOTW game data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath


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
    if handoff.get("title_id") != "01007EF00011E000" or handoff.get("package_version") != "v1114112":
        fail("handoff is not the registered BOTW 1.9.0 profile.")
    if handoff.get("nx2apple_tag") != "v1.3.1-rc2":
        fail("unsupported NX2Apple tag in handoff.")
    if handoff.get("engine_pin") != "81906931262fb25d774cce8bca2db8926439e5a2":
        fail("unexpected NXNative engine pin in handoff.")

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
    archive = root / "botw-work.tar.zst"
    print("[Link2iOS] Downloading prepared workspace...")
    download_drive_file(api, handoff["work_archive"], archive)
    work = root / "work"
    print("[Link2iOS] Verifying and extracting workspace...")
    extract_verified_archive(archive, work)
    archive.unlink()

    nsp_dir = root / "input-nsps"
    nsp_dir.mkdir()
    for index, item in enumerate(handoff["source_files"], start=1):
        filename = Path(item["name"]).name
        local = nsp_dir / f"{item['category']}_{index:02d}_{filename}"
        download_drive_file(api, item, local)
    keys_path = root / "keys" / "prod.keys"
    download_drive_file(api, handoff["prod_keys"], keys_path)

    prep = json.loads((work / "link2ios-linux-prep.json").read_text(encoding="utf-8"))
    if prep.get("engine_pin") != handoff["engine_pin"]:
        fail("workspace engine pin differs from the handoff.")
    if prep.get("package_version") != handoff["package_version"]:
        fail("workspace package version differs from the handoff.")

    romfs_rel = PurePosixPath(handoff["game_data"]["romfs_relative_path"])
    if romfs_rel.is_absolute() or ".." in romfs_rel.parts:
        fail("invalid RomFS path in handoff.")
    romfs_path = work.joinpath(*romfs_rel.parts)
    print("[Link2iOS] Restoring external RomFS into the temporary macOS workspace...")
    download_drive_file(api, handoff["game_data"]["romfs"], romfs_path)

    aoc_dir = work / "aoc"
    aoc_dir.mkdir(parents=True, exist_ok=True)
    for item in handoff["game_data"]["aoc"]:
        filename = Path(item["name"]).name
        if not filename.lower().endswith(".img"):
            fail(f"unexpected AOC image name: {filename}")
        download_drive_file(api, item, aoc_dir / filename)

    if not list(nsp_dir.glob("*.nsp")):
        fail("no NSP source files reached the macOS runner.")
    prepared = {
        "project": "Link2iOS",
        "title_id": handoff["title_id"],
        "package_version": handoff["package_version"],
        "engine_pin": handoff["engine_pin"],
        "nx2apple_tag": handoff["nx2apple_tag"],
        "request_id": handoff["request_id"],
        "nsp_dir": str(nsp_dir),
        "keys": str(keys_path),
        "work_dir": str(work),
        "romfs_path": str(romfs_path),
        "aoc_count": len(handoff["game_data"]["aoc"]),
        "game_data": handoff["game_data"],
    }
    prepared_path = root / "actions-input.json"
    prepared_path.write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(prepared, indent=2))
    print(f"[Link2iOS] Verified inputs and external game data. Build manifest: {prepared_path}")


if __name__ == "__main__":
    main()
