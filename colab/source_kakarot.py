#!/usr/bin/env python3
"""Kakarot package acquisition for Colab. Base and update may independently be NSP or XCI."""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import unquote

FOLDER_MIME = "application/vnd.google-apps.folder"
PACKAGE_SUFFIXES = {".nsp", ".xci"}

def fail(message: str) -> None:
    raise SystemExit("[KaKaRoTiOS] ERROR: " + message)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def validate_package(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in PACKAGE_SUFFIXES:
        fail(f"{path.name}: expected .nsp or .xci.")
    if not path.is_file() or path.stat().st_size < 0x104:
        fail(f"{path.name}: package is missing or too small.")
    with path.open("rb") as stream:
        header = stream.read(0x104)
    if header[:4] == b"PFS0":
        detected = "NSP"
    elif header[0x100:0x104] == b"HEAD":
        detected = "XCI"
    else:
        fail(f"{path.name}: invalid package header (expected NSP PFS0 or XCI HEAD at 0x100).")
    expected = "XCI" if suffix == ".xci" else "NSP"
    if detected != expected:
        fail(f"{path.name}: file extension says {expected}, header says {detected}. Rename only after checking the source.")
    return detected

def download_url(url: str, destination: Path, retries: int = 10) -> dict:
    import requests
    if not url or not url.startswith(("https://", "http://")):
        fail(f"No valid direct download URL supplied for {destination.name}.")
    fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()
    part = destination.with_suffix(destination.suffix + ".part")
    part_source = destination.with_suffix(destination.suffix + ".part.urlsha256")
    if part.exists():
        old_source = part_source.read_text(encoding="utf-8").strip() if part_source.exists() else ""
        if old_source != fingerprint:
            part.unlink(missing_ok=True)
    part_source.write_text(fingerprint + "\\n", encoding="utf-8")
    meta_path = destination.with_suffix(destination.suffix + ".source.json")
    if destination.is_file() and meta_path.is_file():
        try:
            old = json.loads(meta_path.read_text(encoding="utf-8"))
            if old.get("url_sha256") == fingerprint and old.get("size") == destination.stat().st_size:
                kind = validate_package(destination)
                digest = sha256_file(destination)
                if old.get("sha256") == digest:
                    print(f"[KaKaRoTiOS] Reusing verified {kind}: {destination.name} ({destination.stat().st_size:,} bytes; SHA-256 {digest}).", flush=True)
                    return {"name": destination.name, "type": kind, "size": destination.stat().st_size,
                            "sha256": digest, "url_sha256": fingerprint}
        except (OSError, ValueError):
            pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = part.stat().st_size if part.exists() else 0
    last_error = None
    for attempt in range(1, retries + 1):
        headers = {"User-Agent": "Mozilla/5.0"}
        offset = part.stat().st_size if part.exists() else 0
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            print(f"[KaKaRoTiOS] Downloading {destination.name}; attempt {attempt}/{retries}; resume offset {offset:,} bytes.", flush=True)
            with requests.get(url, headers=headers, stream=True, allow_redirects=True,
                              timeout=(30, 180)) as response:
                if response.status_code == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {offset}-"):
                        raise RuntimeError(f"server returned unexpected Content-Range {content_range!r}")
                    mode = "ab"
                elif response.status_code == 200:
                    mode = "wb"
                    offset = 0
                else:
                    response.raise_for_status()
                    raise RuntimeError(f"unexpected HTTP status {response.status_code}")
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    raise RuntimeError("download returned HTML, not a package; use a direct file-download URL")
                response.raise_for_status()
                total = offset + int(response.headers.get("Content-Length") or 0)
                written = offset
                with part.open(mode) as output:
                    for block in response.iter_content(chunk_size=16 * 1024 * 1024):
                        if block:
                            output.write(block)
                            written += len(block)
                if total and written != total:
                    raise RuntimeError(f"short transfer: expected {total:,} bytes, received {written:,}")
            kind = validate_package(part)
            digest = sha256_file(part)
            part.replace(destination)
            part_source.unlink(missing_ok=True)
            record = {"url_sha256": fingerprint, "name": destination.name, "type": kind,
                      "size": destination.stat().st_size, "sha256": digest}
            meta_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            print(f"[KaKaRoTiOS] Download verified: {destination.name}; {record['size']:,} bytes; SHA-256 {digest}.", flush=True)
            return record
        except Exception as exc:
            last_error = exc
            current = part.stat().st_size if part.exists() else 0
            print(f"[KaKaRoTiOS] Download interrupted at {current:,} bytes ({type(exc).__name__}: {exc}).", flush=True)
            if attempt < retries:
                delay = min(2 ** min(attempt, 5), 30)
                print(f"[KaKaRoTiOS] Retrying in {delay}s; partial data is retained for HTTP Range resume.", flush=True)
                time.sleep(delay)
    raise RuntimeError(f"Could not download {destination.name} after {retries} attempts: {last_error}") from last_error

def list_children(api, parent_id: str) -> list[dict]:
    items, token = [], None
    while True:
        page = api.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000, pageToken=token, orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items.extend(page.get("files", []))
        token = page.get("nextPageToken")
        if not token:
            return items

def get_or_create_folder(api, name: str, parent_id: str) -> dict:
    found = [x for x in list_children(api, parent_id)
             if x.get("mimeType") == FOLDER_MIME and x.get("name", "").lower() == name.lower()]
    if len(found) > 1:
        fail(f"More than one Drive/{name} folder exists; keep one to avoid writing to the wrong workspace.")
    if found:
        return found[0]
    result = api.files().create(
        body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        fields="id,name", supportsAllDrives=True).execute()
    return result

def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    with part.open("wb") as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"[KaKaRoTiOS] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
    size = part.stat().st_size
    if size <= 0:
        part.unlink(missing_ok=True)
        fail(f"Drive returned an empty {item.get('name', 'file')}.")
    expected_size = int(item.get("size", size))
    if size != expected_size:
        part.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item.get('name')}: expected {expected_size}, received {size}.")
    part.replace(destination)

def prepare_source(api, drive_root_id: str, runtime_root: Path,
                   base_url: str, update_url: str,
                   base_filename: str = "base.nsp",
                   update_filename: str = "update.nsp") -> dict:
    """Download the two user-supplied URLs and obtain prod.keys from Drive root or Drive/kakarot."""
    if base_filename.lower() == update_filename.lower():
        fail("Base and update must use different filenames to avoid overwriting one another.")
    for label, filename in (("base", base_filename), ("update", update_filename)):
        if Path(filename).name != filename or Path(filename).suffix.lower() not in PACKAGE_SUFFIXES:
            fail(f"{label}_filename must be a simple filename ending in .nsp or .xci.")
    folder = get_or_create_folder(api, "kakarot", drive_root_id)
    root_items = list_children(api, drive_root_id)
    game_items = list_children(api, folder["id"])
    root_keys = [x for x in root_items if x.get("name", "").lower() == "prod.keys"
                 and x.get("mimeType") != FOLDER_MIME]
    game_keys = [x for x in game_items if x.get("name", "").lower() == "prod.keys"
                 and x.get("mimeType") != FOLDER_MIME]
    if len(root_keys) > 1 or len(game_keys) > 1 or not (root_keys or game_keys):
        fail(f"Expected one prod.keys in Drive root or Drive/kakarot; found {len(root_keys)} in root and {len(game_keys)} in kakarot.")
    if root_keys and game_keys:
        fail("prod.keys exists in both Drive root and Drive/kakarot; keep just one authoritative copy.")
    keys_item = (game_keys or root_keys)[0]

    input_dir = runtime_root / "input-packages"
    keys_path = runtime_root / "keys" / "prod.keys"
    input_dir.mkdir(parents=True, exist_ok=True)
    keys_path.parent.mkdir(parents=True, exist_ok=True)
    download_drive_file(api, keys_item, keys_path)
    if keys_path.stat().st_size < 1024:
        fail("prod.keys is unexpectedly small; check that the correct key file is stored in Drive.")
    base_record = download_url(base_url, input_dir / base_filename)
    update_record = download_url(update_url, input_dir / update_filename)
    if base_record["type"] not in ("NSP", "XCI") or update_record["type"] not in ("NSP", "XCI"):
        fail("Both packages must be standard NSP or XCI files.")
    if base_record["sha256"] == update_record["sha256"]:
        fail("Base and update downloads have identical SHA-256; check the two URLs.")
    source = {
        "package_dir": str(input_dir),
        "keys_path": str(keys_path),
        "source_folder_id": folder["id"],
        "source_folder_name": folder["name"],
        "package_count": 2,
        "base": base_record,
        "update": update_record,
        "input_nsp_count": int(base_record["type"] == "NSP") + int(update_record["type"] == "NSP"),
        "input_xci_count": int(base_record["type"] == "XCI") + int(update_record["type"] == "XCI"),
        "keys_drive_id": keys_item["id"],
    }
    source_path = runtime_root / "source-manifest.json"
    source_path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(f"[KaKaRoTiOS] Input set: base {base_record['type']} + update {update_record['type']}; source package bytes {base_record['size'] + update_record['size']:,}.", flush=True)
    print("[KaKaRoTiOS] prod.keys stays in Colab and is excluded from the workspace archive.", flush=True)
    return source
