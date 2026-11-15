#!/usr/bin/env python3
"""One Piece: Pirate Warriors 4 acquisition: one base NSP, one update NSP and 44 named DLC NSPs from Drive/mugi."""
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
CHUNK = 64 * 1024 * 1024

def fail(message: str) -> None:
    raise SystemExit("[Mugiwara4iOS] ERROR: " + message)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def validate_package(path: Path, expected_suffix: str | None = None) -> str:
    suffix = (expected_suffix or path.suffix).lower()
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
    meta_path = destination.with_suffix(destination.suffix + ".source.json")
    if destination.is_file() and meta_path.is_file():
        try:
            old = json.loads(meta_path.read_text(encoding="utf-8"))
            if old.get("url_sha256") == fingerprint and old.get("size") == destination.stat().st_size:
                kind = validate_package(destination)
                digest = sha256_file(destination)
                if old.get("sha256") == digest:
                    print(f"[Mugiwara4iOS] Reusing verified {kind}: {destination.name} ({destination.stat().st_size:,} bytes; SHA-256 {digest}).", flush=True)
                    return {"name": destination.name, "type": kind, "size": destination.stat().st_size,
                            "sha256": digest, "url_sha256": fingerprint}
        except (OSError, ValueError):
            pass
    if part.exists():
        old_source = part_source.read_text(encoding="utf-8").strip() if part_source.exists() else ""
        if old_source != fingerprint:
            part.unlink(missing_ok=True)
    part_source.write_text(fingerprint + chr(10), encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = part.stat().st_size if part.exists() else 0
    last_error = None
    for attempt in range(1, retries + 1):
        headers = {"User-Agent": "Mozilla/5.0"}
        offset = part.stat().st_size if part.exists() else 0
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            print(f"[Mugiwara4iOS] Downloading {destination.name}; attempt {attempt}/{retries}; resume offset {offset:,} bytes.", flush=True)
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
                    if response.status_code in (401, 403):
                        fail(f"The signed URL for {destination.name} was rejected (HTTP {response.status_code}); it may have expired. Replace the signed URL in the notebook and rerun. Any already-persisted base/update in Drive/mugi will be reused.")
                    response.raise_for_status()
                    raise RuntimeError(f"unexpected HTTP status {response.status_code}")
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    raise RuntimeError("download returned HTML, not a package; use a direct file-download URL")
                response.raise_for_status()
                length = response.headers.get("Content-Length")
                if length is not None:
                    total = offset + int(length)
                else:
                    match = re.match(r"bytes\s+\d+-\d+/(\d+|\*)", response.headers.get("Content-Range", ""))
                    total = int(match.group(1)) if match and match.group(1) != "*" else 0
                written = offset
                with part.open(mode) as output:
                    for block in response.iter_content(chunk_size=16 * 1024 * 1024):
                        if block:
                            output.write(block)
                            written += len(block)
                if total and written != total:
                    raise RuntimeError(f"short transfer: expected {total:,} bytes, received {written:,}")
            kind = validate_package(part, destination.suffix)
            digest = sha256_file(part)
            part.replace(destination)
            part_source.unlink(missing_ok=True)
            record = {"url_sha256": fingerprint, "name": destination.name, "type": kind,
                      "size": destination.stat().st_size, "sha256": digest}
            meta_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            print(f"[Mugiwara4iOS] Download verified: {destination.name}; {record['size']:,} bytes; SHA-256 {digest}.", flush=True)
            return record
        except Exception as exc:
            last_error = exc
            current = part.stat().st_size if part.exists() else 0
            print(f"[Mugiwara4iOS] Download interrupted at {current:,} bytes ({type(exc).__name__}: {exc}).", flush=True)
            if attempt < retries:
                delay = min(2 ** min(attempt, 5), 30)
                print(f"[Mugiwara4iOS] Retrying in {delay}s; partial data is retained for HTTP Range resume.", flush=True)
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

def download_drive_file(api, item: dict, destination: Path) -> dict:
    """Download a Drive object to the mugi workspace and verify its size/MD5 when Drive supplies it."""
    from googleapiclient.http import MediaIoBaseDownload
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected_size = int(item.get("size") or 0)
    expected_md5 = str(item.get("md5Checksum") or "").lower()
    if destination.is_file() and expected_size and destination.stat().st_size == expected_size:
        if not expected_md5:
            digest = sha256_file(destination)
            return {"id": item["id"], "name": item["name"], "size": expected_size, "sha256": digest}
        md5 = hashlib.md5()
        with destination.open("rb") as stream:
            for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
                md5.update(block)
        if md5.hexdigest().lower() == expected_md5:
            return {"id": item["id"], "name": item["name"], "size": expected_size,
                    "sha256": sha256_file(destination)}
    part = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    digest = hashlib.sha256()
    total = 0
    from http.client import IncompleteRead
    with part.open("wb") as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
        done, retries = False, 0
        while not done:
            try:
                status, done = downloader.next_chunk()
                retries = 0
            except (IncompleteRead, TimeoutError, ConnectionError, OSError) as exc:
                retries += 1
                if retries > 10:
                    raise RuntimeError(f"Drive download failed after {retries-1} retries at {downloader._progress}: {exc}") from exc
                delay = min(2 ** min(retries, 5), 30)
                print(f"[Mugiwara4iOS] Drive transfer interrupted at {downloader._progress}; retry {retries}/10 in {delay}s.", flush=True)
                time.sleep(delay)
                continue
            if status:
                print(f"[Mugiwara4iOS] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
    with part.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block); total += len(block)
    if not total or (expected_size and total != expected_size):
        part.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item.get('name')}: expected {expected_size}, received {total}.")
    if expected_md5:
        md5 = hashlib.md5()
        with part.open("rb") as stream:
            for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
                md5.update(block)
        if md5.hexdigest().lower() != expected_md5:
            part.unlink(missing_ok=True)
            fail(f"Drive MD5 mismatch for {item.get('name')}.")
    part.replace(destination)
    return {"id": item["id"], "name": item["name"], "size": total, "sha256": digest.hexdigest()}

def upload_drive_file(api, path: Path, parent_id: str, drive_name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    size = path.stat().st_size
    if size <= 0:
        fail(f"Refusing to upload an empty package: {path.name}.")
    media = MediaFileUpload(str(path), mimetype="application/octet-stream", chunksize=CHUNK, resumable=True)
    request = api.files().create(
        body={"name": drive_name, "parents": [parent_id]}, media_body=media,
        fields="id,name,size", supportsAllDrives=True)
    item = None
    while item is None:
        status, item = request.next_chunk()
        if status:
            print(f"[Mugiwara4iOS] Uploading {drive_name}: {status.progress()*100:.1f}%", flush=True)
    if int(item.get("size", -1)) != size:
        fail(f"Drive upload size mismatch for {drive_name}: {item.get('size')} != {size}.")
    record = {"id": item["id"], "name": item["name"], "size": size, "sha256": sha256_file(path)}
    print(f"[Mugiwara4iOS] Persisted {drive_name} inside Drive/mugi ({size:,} bytes; SHA-256 {record['sha256']}).", flush=True)
    return record

def safe_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return value or "dlc.nsp"

def exact_files(items: list[dict], name: str) -> list[dict]:
    return [item for item in items if item.get("mimeType") != FOLDER_MIME
            and item.get("name", "").casefold() == name.casefold()]

def source_folder(api, drive_root_id: str) -> tuple[dict, list[dict]]:
    root_items = list_children(api, drive_root_id)
    folders = [item for item in root_items if item.get("mimeType") == FOLDER_MIME
               and item.get("name", "").casefold() == "mugi"]
    if len(folders) != 1:
        fail(f"Expected exactly one Drive/{'mugi'} folder in the configured parent; found {len(folders)}.")
    folder = folders[0]
    return folder, list_children(api, folder["id"])

def prepare_source(api, drive_root_id: str, runtime_root: Path,
                   base_url: str, update_url: str,
                   base_filename: str = "Mugiwara4iOS_BASE_v0.nsp",
                   update_filename: str = "Mugiwara4iOS_UPDATE_v1.8.7.nsp") -> dict:
    """Use only Drive/<configured parent>/mugi: prod.keys + 44 arbitrarily named DLC NSPs.

    The two signed base/update links are downloaded once and persisted back into mugi
    under stable, versioned names, so a resumed Colab session does not depend on an
    expiring URL. Existing canonical files are reused after header/hash validation.
    """
    if base_filename.casefold() == update_filename.casefold():
        fail("The reserved base and update filenames must be different.")
    for label, filename in (("base", base_filename), ("update", update_filename)):
        if Path(filename).name != filename or Path(filename).suffix.lower() != ".nsp":
            fail(f"The {label} must use a simple .nsp filename: {filename!r}.")

    folder, items = source_folder(api, drive_root_id)
    root = runtime_root.resolve()
    input_dir = root / "input-packages"
    keys_path = root / "keys" / "prod.keys"
    input_dir.mkdir(parents=True, exist_ok=True)
    keys_path.parent.mkdir(parents=True, exist_ok=True)

    key_items = exact_files(items, "prod.keys")
    if len(key_items) != 1:
        fail(f"Drive/mugi must contain exactly one prod.keys; found {len(key_items)}.")
    keys_record = download_drive_file(api, key_items[0], keys_path)
    if keys_path.stat().st_size < 1024:
        fail("Drive/mugi/prod.keys is unexpectedly small; refusing to proceed.")

    base_drive = exact_files(items, base_filename)
    update_drive = exact_files(items, update_filename)
    if len(base_drive) > 1 or len(update_drive) > 1:
        fail("Drive/mugi contains duplicate reserved base/update filenames; remove the duplicate before proceeding.")

    def obtain_linked(label: str, url: str, drive_records: list[dict], drive_name: str, local_name: str) -> dict:
        target = input_dir / local_name
        if drive_records:
            rec = download_drive_file(api, drive_records[0], target)
            kind = validate_package(target, ".nsp")
            print(f"[Mugiwara4iOS] Reusing persisted {label} from Drive/mugi/{drive_name}; signed URL not needed.", flush=True)
            return {**rec, "name": target.name, "drive_name": drive_name, "type": kind,
                    "source": "drive-cache", "url_sha256": ""}
        if not url or not url.startswith(("https://", "http://")):
            fail(f"The signed {label} NSP URL is missing and Drive/mugi has no persisted {drive_name}.")
        rec = download_url(url, target)
        kind = validate_package(target, ".nsp")
        uploaded = upload_drive_file(api, target, folder["id"], drive_name)
        # Refresh the file inventory only after the upload succeeded; its stable name is now cached in mugi.
        return {**uploaded, "name": target.name, "drive_name": drive_name, "type": kind,
                "source": "signed-url", "url_sha256": rec.get("url_sha256", "")}

    base_record = obtain_linked("base", base_url, base_drive, base_filename, "000_base.nsp")
    update_record = obtain_linked("update", update_url, update_drive, update_filename, "001_update.nsp")
    if base_record["sha256"] == update_record["sha256"]:
        fail("Base and update have identical SHA-256; the two supplied links appear to point to the same package.")

    reserved_names = {base_filename.casefold(), update_filename.casefold()}
    dlc_items = sorted(
        (item for item in items if item.get("mimeType") != FOLDER_MIME
         and Path(item.get("name", "")).suffix.lower() == ".nsp"
         and item.get("name", "").casefold() not in reserved_names
         and item.get("name", "").casefold() != "prod.keys"),
        key=lambda item: (item.get("name", "").casefold(), item.get("id", "")),
    )
    xci_items = [item for item in items if item.get("mimeType") != FOLDER_MIME
                 and Path(item.get("name", "")).suffix.lower() == ".xci"]
    if xci_items:
        fail("Drive/mugi must contain the 44 DLCs as .nsp files; unexpected XCI files: "
             + ", ".join(x.get("name", "(unnamed)") for x in xci_items[:10]))
    if len(dlc_items) != 44:
        fail(f"Expected exactly 44 DLC NSP files in Drive/mugi (any filenames are accepted); found {len(dlc_items)}: "
             + ", ".join(x.get("name", "(unnamed)") for x in dlc_items[:12]))
    names = [str(item.get("name", "")) for item in dlc_items]
    if len({name.casefold() for name in names}) != len(names):
        fail("Drive/mugi has duplicate DLC filenames; rename the duplicates so every source file is unambiguous.")

    # Keep stable local ordering for the NSP reader; source filenames are retained in the manifest.
    packages = [{"role": "base", "drive_name": base_filename, "local_name": "000_base.nsp", **base_record},
                {"role": "update", "drive_name": update_filename, "local_name": "001_update.nsp", **update_record}]
    dlc_records = []
    for index, item in enumerate(dlc_items, start=2):
        local_name = f"{index:03d}_{safe_name(item['name'])}"
        target = input_dir / local_name
        record = download_drive_file(api, item, target)
        validate_package(target, ".nsp")
        row = {"role": "dlc", "drive_name": item["name"], "local_name": local_name,
               "type": "NSP", "size": record["size"], "sha256": record["sha256"],
               "drive_id": item["id"]}
        dlc_records.append(row)
        packages.append(row)

    # Delete stale package files left by an interrupted/older preparation, never unrelated files in mugi.
    expected_local = {item["local_name"] for item in packages}
    for old in input_dir.iterdir():
        if old.is_file() and old.suffix.lower() in PACKAGE_SUFFIXES and old.name not in expected_local:
            old.unlink()
    if len(packages) != 46 or len(dlc_records) != 44:
        fail(f"Internal package inventory error: expected 46 packages/44 DLCs, found {len(packages)}/{len(dlc_records)}.")
    total_bytes = sum(int(item["size"]) for item in packages)
    source = {
        "package_dir": str(input_dir), "keys_path": str(keys_path),
        "source_folder_id": folder["id"], "source_folder_name": folder["name"],
        "package_count": 46, "base_type": "NSP", "base_extension": ".nsp",
        "base_file_name": "000_base.nsp", "update_file_name": "001_update.nsp",
        "input_nsp_count": 46, "input_xci_count": 0,
        "update_nsp_count": 1, "dlc_nsp_count": 44,
        "base": base_record, "update": update_record,
        "dlc_files": dlc_records, "packages": packages,
        "keys_drive_id": keys_item["id"], "keys_sha256": keys_record["sha256"],
        "total_package_bytes": total_bytes,
    }
    source_path = root / "source-manifest.json"
    source_path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    source["manifest_path"] = str(source_path)
    print("[Mugiwara4iOS] Source verified exclusively in Drive/mugi:", flush=True)
    print("  Base NSP:", base_record["size"], "bytes; SHA-256", base_record["sha256"], flush=True)
    print("  Update NSP v1.8.7 input:", update_record["size"], "bytes; SHA-256", update_record["sha256"], flush=True)
    print("  DLC NSPs:", len(dlc_records), "(filenames are not assumed to be dlc1..dlc44)", flush=True)
    print("  Total source packages:", len(packages), f"({total_bytes/2**30:.2f} GiB)", flush=True)
    print("  prod.keys: kept locally for this preparation and excluded from the Drive workspace archive.", flush=True)
    return source
