#!/usr/bin/env python3
"""Fetch Blades of Time base and update NSP from verified Drive folder botime."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath

FOLDER_MIME = "application/vnd.google-apps.folder"
CHUNK = 64 * 1024 * 1024


def fail(message: str) -> None:
    raise SystemExit("[BladesTime] ERROR: " + message)


def list_children(api, parent_id: str) -> list[dict]:
    files, token = [], None
    while True:
        page = api.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000,
            pageToken=token,
            orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,modifiedTime,md5Checksum)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files.extend(page.get("files", []))
        token = page.get("nextPageToken")
        if not token:
            return files


def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = int(item.get("size") or 0)
    expected_md5 = str(item.get("md5Checksum") or "").lower()
    if destination.is_file() and expected and destination.stat().st_size == expected:
        if expected_md5:
            digest = hashlib.md5()
            with destination.open("rb") as stream:
                for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest().lower() == expected_md5:
                print(f"[BladesTime] Reutilizando {item['name']}: {expected:,} bytes verificados (MD5 Drive).")
                return
        else:
            print(f"[BladesTime] Reutilizando {item['name']}: {expected:,} bytes (tamanho conferido).")
            return
    partial = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    started = time.monotonic()
    with partial.open("wb") as output:
        downloader = MediaIoBaseDownload(output, request, chunksize=CHUNK)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"[BladesTime] Drive {item['name']}: {status.progress() * 100:.1f}%")
    if expected and partial.stat().st_size != expected:
        partial.unlink(missing_ok=True)
        fail(f"tamanho incorreto ao baixar {item['name']} do Drive.")
    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        fail(f"o arquivo {item['name']} baixado do Drive está vazio.")
    if expected_md5:
        check = hashlib.md5()
        with partial.open("rb") as stream:
            for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
                check.update(block)
        if check.hexdigest().lower() != expected_md5:
            partial.unlink(missing_ok=True)
            fail(f"Drive MD5 mismatch after download: {item['name']}")
    partial.replace(destination)
    elapsed = max(time.monotonic() - started, 0.001)
    size = destination.stat().st_size
    print(
        f"[BladesTime] Download concluído: {item['name']} — {size:,} bytes "
        f"({size / 1024**3:.2f} GiB), {elapsed:.1f}s, "
        f"{size / elapsed / 1024**2:.1f} MiB/s."
    )



TITLE_ID = "0100CFA00CC74000"
BASE_SOURCE_ID = "1Xj8-gmznW5Pk6fnnqjsH4wZAfmAl065U"
UPDATE_SOURCE_ID = "1HzAcKAyJTDJ9kVTPoyvOuJVSpExyv-3j"
GAME_FOLDER_ID = "18G7EletOjZZ-eTtdPdM2ZPZsKVymHsZt"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def prepare_source(api, drive_folder_id: str, runtime_root: Path) -> dict:
    """Stage exactly one base NSP and one update from the verified botime folder."""
    root = list_children(api, drive_folder_id)
    folder = next((x for x in root if x["id"] == GAME_FOLDER_ID and
                   x.get("mimeType") == FOLDER_MIME and x["name"].casefold() == "botime"), None)
    if not folder:
        fail("botime was not found in the expected parent Drive folder")
    children = list_children(api, folder["id"])
    nsp = [x for x in children if x.get("mimeType") != FOLDER_MIME
           and x["name"].lower().endswith(".nsp")]
    if len(nsp) != 2:
        fail(f"expected exactly 2 NSPs in botime, got {[x['name'] for x in nsp]}")
    base = next((x for x in nsp if x["id"] == BASE_SOURCE_ID), None)
    update = next((x for x in nsp if x["id"] == UPDATE_SOURCE_ID), None)
    if not base or not update or TITLE_ID.lower() not in base["name"].lower() or "[v0]" not in base["name"].lower():
        fail("base/update source identity does not match the verified Drive content")
    if update["name"].lower() != "update.nsp":
        fail("update filename changed; refusing to guess the input")
    keys = next((x for x in children + root if x.get("mimeType") != FOLDER_MIME
                 and x["name"].casefold() == "prod.keys"), None)
    if not keys:
        fail("prod.keys not found in botime or its parent folder")
    key_path = runtime_root / "keys" / "prod.keys"
    download_drive_file(api, keys, key_path)
    package_dir = runtime_root / "input-packages"
    package_dir.mkdir(parents=True, exist_ok=True)
    base_path = package_dir / "000_base_blades.nsp"
    update_path = package_dir / "100_update_blades.nsp"
    download_drive_file(api, base, base_path)
    download_drive_file(api, update, update_path)
    for label, file in (("base", base_path), ("update", update_path)):
        with file.open("rb") as stream:
            if stream.read(4) != b"PFS0":
                fail(f"{label} is not a valid NSP/PFS0; content invalid")
    manifest = {label: {"id": item["id"], "name": item["name"], "size": path.stat().st_size,
                        "sha256": file_sha256(path)}
                for label, item, path in (("base", base, base_path), ("update", update, update_path))}
    print("[BladesTime] Input SHA-256 verified:", manifest, flush=True)
    return {"package_dir": str(package_dir), "keys_path": str(key_path),
            "package_count": 2, "update_nsp_count": 1, "dlc_nsp_count": 0,
            "game_folder_id": folder["id"], "source_files": manifest}
