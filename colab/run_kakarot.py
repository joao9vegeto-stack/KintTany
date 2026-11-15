#!/usr/bin/env python3
"""Colab orchestration: direct package URLs -> NXNative prep -> Drive split-data handoff -> branch-only dispatch."""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import getpass
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "KaKaRoTiOS"
PROJECT = "KaKaRoTiOS"
TITLE_ID = "010051C0134F8000"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
CHUNK = 64 * 1024 * 1024
FOLDER_MIME = "application/vnd.google-apps.folder"
ROOT = Path("/content/kakarot-ios")

def fail(message: str) -> None:
    raise SystemExit("[KaKaRoTiOS] ERROR: " + message)

def drive_api():
    from googleapiclient.discovery import build
    try:
        import google.auth
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    except Exception as exc:
        fail(f"Google Drive is not authenticated; run auth.authenticate_user() first ({type(exc).__name__}: {exc}).")
    return build("drive", "v3", credentials=credentials, cache_discovery=False)

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

def create_folder(api, name: str, parent_id: str) -> str:
    return api.files().create(
        body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        fields="id,name", supportsAllDrives=True).execute()["id"]

def get_or_create_folder(api, name: str, parent_id: str) -> str:
    matches = [x for x in list_children(api, parent_id)
               if x.get("mimeType") == FOLDER_MIME and x.get("name", "").lower() == name.lower()]
    if len(matches) > 1:
        fail(f"More than one Drive/{name} folder exists under the same parent.")
    return matches[0]["id"] if matches else create_folder(api, name, parent_id)

def verify_drive_folder(api, folder_id: str, expected_prefix: str | None = None) -> dict:
    item = api.files().get(fileId=folder_id, fields="id,name,mimeType,trashed,parents",
                           supportsAllDrives=True).execute()
    if item.get("trashed") or item.get("mimeType") != FOLDER_MIME:
        fail(f"Saved Drive folder {folder_id} is missing, trashed or is not a folder.")
    if expected_prefix and not str(item.get("name", "")).startswith(expected_prefix):
        fail(f"Saved Drive folder {folder_id} does not have the expected {expected_prefix!r} name.")
    return item

def persist_source_manifest(source: dict) -> None:
    path = Path(source["package_dir"]).parent / "source-manifest.json"
    path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")

def file_hashes(path: Path) -> dict:
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            sha.update(block)
            md5.update(block)
    return {"sha256": sha.hexdigest(), "md5": md5.hexdigest()}

def sha256_file(path: Path) -> str:
    return file_hashes(path)["sha256"]

def verify_drive_record(api, record: dict) -> None:
    item = api.files().get(fileId=record["id"], fields="id,name,size,md5Checksum,trashed",
                           supportsAllDrives=True).execute()
    if item.get("trashed"):
        fail(f"Drive file {record.get('name')} is trashed.")
    if item.get("name") != record.get("name") or int(item.get("size", -1)) != int(record.get("size", -2)):
        fail(f"Drive metadata mismatch for {record.get('name')}.")
    expected_md5 = str(record.get("md5", "")).lower()
    if expected_md5 and str(item.get("md5Checksum", "")).lower() != expected_md5:
        fail(f"Google Drive md5Checksum mismatch for {record.get('name')}.")
    print(f"[KaKaRoTiOS] Drive metadata verified: {record['name']} ({record['size']:,} bytes; MD5 matches).", flush=True)

def upsert_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    """Create or replace one same-name checkpoint in place; never create ambiguous duplicates."""
    from googleapiclient.http import MediaFileUpload
    size = path.stat().st_size
    if size <= 0:
        fail(f"Refusing to upsert empty file {name}.")
    hashes = file_hashes(path)
    existing = [x for x in list_children(api, parent_id)
                if x.get("mimeType") != FOLDER_MIME and x.get("name") == name]
    if len(existing) > 1:
        fail(f"Drive contains duplicate files named {name}; refusing an ambiguous checkpoint.")
    if not existing:
        return upload_drive_file(api, path, parent_id, name)
    item = existing[0]
    if (int(item.get("size", -1)) == size
            and str(item.get("md5Checksum", "")).lower() == hashes["md5"]):
        record = {"id": item["id"], "name": item["name"], "size": size,
                  "sha256": hashes["sha256"], "md5": hashes["md5"]}
        verify_drive_record(api, record)
        return record
    print(f"[KaKaRoTiOS] Updating Drive checkpoint {name} in place...", flush=True)
    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            chunksize=CHUNK, resumable=True)
    request = api.files().update(fileId=item["id"], media_body=media,
        fields="id,name,size,md5Checksum", supportsAllDrives=True)
    updated = None
    while updated is None:
        status, updated = request.next_chunk()
        if status:
            print(f"[KaKaRoTiOS] Drive update {name}: {status.progress()*100:.1f}%", flush=True)
    if int(updated.get("size", -1)) != size:
        fail(f"Drive checkpoint update size mismatch for {name}.")
    if updated.get("md5Checksum") and updated["md5Checksum"].lower() != hashes["md5"]:
        fail(f"Drive checkpoint update MD5 mismatch for {name}.")
    record = {"id": updated["id"], "name": updated["name"], "size": size,
              "sha256": hashes["sha256"], "md5": hashes["md5"]}
    verify_drive_record(api, record)
    return record

def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    size = path.stat().st_size
    if size <= 0:
        fail(f"Refusing to upload empty file {name}.")
    hashes = file_hashes(path)
    existing = [x for x in list_children(api, parent_id)
                if x.get("mimeType") != FOLDER_MIME and x.get("name") == name]
    if len(existing) > 1:
        fail(f"Drive contains duplicate files named {name}; refusing an ambiguous resume.")
    if existing:
        item = existing[0]
        if (int(item.get("size", -1)) != size
                or str(item.get("md5Checksum", "")).lower() != hashes["md5"]):
            fail(f"Drive already contains {name}, but its size/MD5 differs from the local source. "
                 "The existing file is preserved; use a fresh KaKaRoTiOS run folder.")
        record = {"id": item["id"], "name": item["name"], "size": size,
                  "sha256": hashes["sha256"], "md5": hashes["md5"]}
        verify_drive_record(api, record)
        print(f"[KaKaRoTiOS] Reusing already verified Drive file {name}; no duplicate upload.", flush=True)
        return record
    print(f"[KaKaRoTiOS] Uploading {name}: {size:,} bytes ({size/2**30:.2f} GiB)...", flush=True)
    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            chunksize=CHUNK, resumable=True)
    request = api.files().create(
        body={"name": name, "parents": [parent_id]}, media_body=media,
        fields="id,name,size,md5Checksum", supportsAllDrives=True)
    item = None
    while item is None:
        status, item = request.next_chunk()
        if status:
            print(f"[KaKaRoTiOS] Drive upload {name}: {status.progress()*100:.1f}%", flush=True)
    if int(item.get("size", -1)) != size:
        fail(f"Drive upload size mismatch for {name}.")
    if item.get("md5Checksum") and item["md5Checksum"].lower() != hashes["md5"]:
        fail(f"Google Drive md5Checksum differs from the local file for {name}.")
    record = {"id": item["id"], "name": item["name"], "size": size,
              "sha256": hashes["sha256"], "md5": hashes["md5"]}
    verify_drive_record(api, record)
    print(f"[KaKaRoTiOS] Upload verified: {name}; size + Google Drive MD5 + local SHA-256 {hashes['sha256']}.", flush=True)
    return record

def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    with part.open("wb") as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
        done, retries = False, 0
        while not done:
            try:
                status, done = downloader.next_chunk()
                retries = 0
            except (TimeoutError, ConnectionError, OSError) as exc:
                retries += 1
                if retries > 10:
                    raise RuntimeError(f"Drive download failed after {retries-1} retries: {exc}") from exc
                delay = min(2 ** min(retries, 5), 30)
                print(f"[KaKaRoTiOS] Drive transfer interrupted at {downloader._progress}; retry {retries}/10 in {delay}s.", flush=True)
                time.sleep(delay)
                continue
            if status:
                print(f"[KaKaRoTiOS] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
    size = part.stat().st_size
    if size != int(item.get("size", -1)):
        part.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item.get('name')}: received {size}, expected {item.get('size')}.")
    digest = sha256_file(part)
    if digest.lower() != str(item.get("sha256", "")).lower():
        part.unlink(missing_ok=True)
        fail(f"Drive SHA-256 mismatch for {item.get('name')}.")
    part.replace(destination)

def build_work_archive(work: Path, destination: Path) -> None:
    """Archive only reproducible workspace outputs; RomFS is stored as a separate Drive object."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "tar", "-C", str(work),
        "--exclude=./tools", "--exclude=./tmp",
        "--exclude=./extract/*/RomFS.img", "--exclude=*/RomFS.img",
        "--exclude=./extract/*/RomFS.img.part",
        "--exclude=./aoc", "--exclude=aoc",
        "-cf", "-", ".",
    ]
    tar = subprocess.Popen(command, stdout=subprocess.PIPE)
    if tar.stdout is None:
        fail("Could not open the workspace tar stream.")
    try:
        compressed = subprocess.run(["zstd", "-T0", "-8", "-o", str(destination)],
            stdin=tar.stdout, check=False)
    finally:
        tar.stdout.close()
    if tar.wait() != 0 or compressed.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        fail("Could not create the zstd workspace archive.")

def install_nx2apple(root: Path) -> Path:
    nx = root / "NX2Apple"
    pin_file = nx / ".upstream-ref"
    if (not nx.is_dir() or not pin_file.is_file()
            or pin_file.read_text(encoding="utf-8").strip() != ENGINE_PIN):
        shutil.rmtree(nx, ignore_errors=True)
        print(f"[KaKaRoTiOS] Cloning NX2Apple {NX2APPLE_TAG}; syncing the exact NXNative pin {ENGINE_PIN}...", flush=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", NX2APPLE_TAG,
                        "https://github.com/LNPANDY/NX2Apple.git", str(nx)], check=True)
        subprocess.run([sys.executable, str(nx / "tools" / "engine.py"), "sync"], cwd=nx, check=True)
    pin = pin_file.read_text(encoding="utf-8").strip()
    if pin != ENGINE_PIN:
        fail(f"NXNative engine pin mismatch: {pin}; expected {ENGINE_PIN}.")
    return nx

def prepare(args, api=None) -> dict:
    api = api or drive_api()
    ROOT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    # Use the package-qualified module shared with the notebook preflight.
    # This prevents a stale top-level "source_kakarot" in sys.modules from
    # shadowing the freshly fetched branch source after a Colab rerun.
    from .source_kakarot import cleanup_rar_parts, prepare_source
    source = prepare_source(
        api, args.drive_folder_id, ROOT,
        args.base_part_urls, args.update_package_url,
        args.base_part_names,
    )
    input_dir, keys = Path(source["package_dir"]), Path(source["keys_path"])
    base_path, update_path = Path(source["base_path"]), Path(source["update_path"])
    # The 20 DLC files are direct children of Drive/<configured root>/kakarot.
    # Keep each original filename; do not depend on artificial dlc1/dlc2 names.
    kakarot_id = source["drive_kakarot_folder_id"]
    dlc_items = sorted(
        (x for x in list_children(api, kakarot_id)
         if x.get("mimeType") != FOLDER_MIME
         and Path(x.get("name", "")).suffix.lower() in (".nsp", ".xci")
         and x.get("name", "").lower() not in {
             base_path.name.lower(), update_path.name.lower(),
             "base.nsp", "base.xci", "update.nsp", "update.xci",
         }),
        key=lambda x: str(x.get("name", "")).casefold(),
    )
    if len(dlc_items) != 20:
        inventory = "; ".join(
            f"{x.get('name')} ({int(x.get('size') or 0):,} bytes)"
            for x in dlc_items
        )
        fail(f"Expected exactly 20 named DLC packages directly inside Drive/kakarot; found {len(dlc_items)}. Found: {inventory or '(none)'}")

    large_group, small_group, other_sizes = [], [], []
    for item in dlc_items:
        size_bytes = int(item.get("size") or 0)
        size_kib = round(size_bytes / 1024)
        if 118 <= size_kib <= 128:
            large_group.append(item)
        elif 100 <= size_kib <= 112:
            small_group.append(item)
        else:
            other_sizes.append(item)
    if len(large_group) != 17 or len(small_group) != 3 or other_sizes:
        inventory = "; ".join(
            f"{x.get('name')} ({int(x.get('size') or 0):,} bytes; {int(round(int(x.get('size') or 0)/1024))} KiB)"
            for x in dlc_items
        )
        fail("The 20 DLC file sizes do not match the stated inventory (17 around 124 KB and 3 around 106 KB). Drive inventory: " + inventory)
    duplicate_names = sorted({
        str(x.get("name", "")).casefold() for x in dlc_items
        if sum(1 for y in dlc_items if str(y.get("name", "")).casefold() == str(x.get("name", "")).casefold()) > 1
    })
    if duplicate_names:
        fail("Duplicate DLC filenames in Drive/kakarot would collide during staging: " + ", ".join(duplicate_names))

    staged_items = []
    for item in dlc_items:
        original_name = Path(item["name"]).name
        dest = input_dir / ("dlc_" + original_name)
        download_drive_file(api, item, dest)
        with dest.open("rb") as stream:
            header = stream.read(0x104)
        suffix = Path(original_name).suffix.lower()
        valid_header = (
            header[:4] == b"PFS0" if suffix == ".nsp"
            else len(header) >= 0x104 and header[0x100:0x104] == b"HEAD"
        )
        if not valid_header:
            dest.unlink(missing_ok=True)
            fail("Existing DLC file " + original_name + " has an invalid header for its " + suffix + " extension.")
        staged_items.append({
            "id": item["id"], "name": item["name"],
            "size": int(item.get("size") or dest.stat().st_size),
            "local_name": dest.name,
        })
    source["dlc_drive_items"] = staged_items
    source["dlc_inventory"] = {
        "total": len(staged_items),
        "approximately_124_kb": len(large_group),
        "approximately_106_kb": len(small_group),
    }
    print(
        "[KaKaRoTiOS] DLC inventory verified: "
        f"{len(staged_items)} named packages; 17 around 124 KB and 3 around 106 KB. "
        "Original names preserved with only the internal dlc_ scanner prefix.",
        flush=True,
    )
    print(
        f"[KaKaRoTiOS] Reconstructed source pair: base {source['base']['type']} "
        f"({source['base']['size']:,} bytes) + update {source['update']['type']} "
        f"({source['update']['size']:,} bytes).",
        flush=True)

    # Persist the request and Drive folder IDs before large uploads. If Colab
    # stops midway, a retry reuses this same folder and idempotently verifies files.
    request_id = source.get("request_id") or str(uuid.uuid4())
    output_id = source.get("drive_output_folder_id")
    if output_id:
        verify_drive_folder(api, output_id, "KaKaRoTiOS_")
    else:
        output_id = create_folder(api, f"KaKaRoTiOS_{request_id[:8]}", source["drive_kakarot_folder_id"])
        source["request_id"] = request_id
        source["drive_output_folder_id"] = output_id
        persist_source_manifest(source)
    pipeline_id = source.get("drive_pipeline_folder_id") or get_or_create_folder(api, "pipeline", output_id)
    games_id = source.get("drive_games_folder_id") or get_or_create_folder(api, "games", output_id)
    game_id = source.get("drive_game_folder_id") or get_or_create_folder(api, TITLE_ID.lower(), games_id)
    aoc_id = source.get("drive_aoc_folder_id") or get_or_create_folder(api, "aoc", game_id)
    verify_drive_folder(api, pipeline_id)
    verify_drive_folder(api, games_id)
    verify_drive_folder(api, game_id)
    verify_drive_folder(api, aoc_id)
    source.update({
        "request_id": request_id,
        "drive_output_folder_id": output_id,
        "drive_pipeline_folder_id": pipeline_id,
        "drive_games_folder_id": games_id,
        "drive_game_folder_id": game_id,
        "drive_aoc_folder_id": aoc_id,
    })
    persist_source_manifest(source)

    base_record = upload_drive_file(api, base_path, game_id, f"base{base_path.suffix.lower()}")
    update_record = upload_drive_file(api, update_path, game_id, f"update{update_path.suffix.lower()}")
    source["drive_base_package"] = base_record
    source["drive_update_package"] = update_record
    source["rar_parts_cleanup_pending"] = Path(source["archive_dir"]).exists()
    persist_source_manifest(source)
    # Publish a recovery checkpoint before deleting the six RAR parts. A fresh
    # Colab runtime can use these Drive package IDs if the survey is interrupted.
    source_checkpoint = upsert_drive_file(
        api, ROOT / "source-manifest.json", pipeline_id, "source-manifest.json")
    print(f"[KaKaRoTiOS] Drive source checkpoint saved ({source_checkpoint['id']}); now removing local RAR volumes...", flush=True)
    cleanup_rar_parts(source)
    # Keep the checkpoint in sync with the confirmed cleanup state.
    source_checkpoint = upsert_drive_file(
        api, ROOT / "source-manifest.json", pipeline_id, "source-manifest.json")

    nx = install_nx2apple(ROOT)
    work = ROOT / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    from .prepare_kakarot import run_preparation
    prep = run_preparation(argparse.Namespace(
        nx2apple_root=nx, package_dir=input_dir, keys=keys, work_dir=work))
    if prep.get("project") != PROJECT or prep.get("title_id") != TITLE_ID:
        fail("NXNative preparation manifest does not belong to KaKaRoTiOS/Kakarot.")
    if prep.get("nx2apple_tag") != NX2APPLE_TAG or prep.get("engine_pin") != ENGINE_PIN:
        fail("Preparation manifest uses another NX2Apple/NXNative pin.")
    if prep.get("package_version") == "v0":
        fail("NXNative selected the base-only v0 extraction; refusing to continue without the supplied update.")
    scanned_packages = prep.get("input_packages", [])
    scanned_dlcs = [item for item in scanned_packages if str(item.get("name", "")).startswith("dlc_")]
    if (prep.get("input_package_count") != 22 or len(scanned_packages) != 22
            or prep.get("input_dlc_package_count") != 20 or len(scanned_dlcs) != 20):
        fail("NXNative scan must contain exactly base + update + 20 staged DLC packages.")

    romfs_rel = Path(prep["romfs_relative_path"])
    if romfs_rel.is_absolute() or ".." in romfs_rel.parts:
        fail("Unsafe RomFS path in the preparation manifest.")
    romfs = work.joinpath(*romfs_rel.parts)
    romfs_id = work / prep["romfs_id_relative_path"]
    if not romfs.is_file() or romfs.stat().st_size != int(prep["romfs_size"]):
        fail("Extracted RomFS size differs from the preparation manifest.")
    if sha256_file(romfs) != prep["romfs_sha256"]:
        fail("Extracted RomFS SHA-256 differs from the preparation manifest.")
    if not romfs_id.is_file():
        fail("NXNative RomFS identity sidecar is missing.")
    identity = json.loads(romfs_id.read_text(encoding="utf-8"))
    if (identity.get("title") != TITLE_ID.lower()
            or identity.get("version") != prep["package_version"]
            or identity.get("bytes") != prep["romfs_size"]
            or identity.get("sha256") != prep["romfs_sha256"]):
        fail("RomFS identity sidecar does not match the game/version/size/SHA-256.")

    # AOC exists only when NXNative actually finds DLC packages. With base+update
    # only, the folder remains empty; no DLC image is fabricated.
    aoc_dir = work / "aoc"
    aoc_dir.mkdir(parents=True, exist_ok=True)
    local_aoc = sorted(p for p in aoc_dir.glob("*.img") if p.is_file() and not p.is_symlink())
    expected_aoc = prep.get("aoc_images", [])
    if len(local_aoc) != int(prep.get("aoc_count", -1)):
        fail("NXNative AOC count differs from the preparation manifest.")
    aoc_records = []
    for item in expected_aoc:
        path = aoc_dir / item["name"]
        if not path.is_file() or path.stat().st_size != int(item["size"]):
            fail(f"NXNative AOC image is missing or has the wrong size: {item['name']}")
        digest = sha256_file(path)
        if digest != item["sha256"]:
            fail(f"NXNative AOC image SHA-256 mismatch: {item['name']}")
        drive_item = upsert_drive_file(api, path, aoc_id, item["name"])
        if drive_item["sha256"] != digest:
            fail(f"AOC SHA-256 changed during upload: {item['name']}")
        aoc_records.append(drive_item)
    print(f"[KaKaRoTiOS] AOC images found and uploaded: {len(aoc_records)}.", flush=True)

    print("[KaKaRoTiOS] Uploading RomFS.img as a separate Drive object...", flush=True)
    romfs_record = upsert_drive_file(api, romfs, game_id, "romfs.img")
    archive = ROOT / "kakarot-work.tar.zst"
    print("[KaKaRoTiOS] Archiving rewritten ExeFS, provisional profile, survey and audits; excluding source packages, prod.keys, RomFS and AOC.", flush=True)
    build_work_archive(work, archive)
    archive_record = upsert_drive_file(api, archive, pipeline_id, "kakarot-work.tar.zst")

    handoff = {
        "format": 2,
        "project": PROJECT,
        "branch": BRANCH,
        "request_id": request_id,
        "title_id": TITLE_ID,
        "package_version": prep["package_version"],
        "nx2apple_tag": NX2APPLE_TAG,
        "engine_pin": ENGINE_PIN,
        "drive_output_folder_id": output_id,
        "drive_output_folder_url": f"https://drive.google.com/drive/folders/{output_id}",
        "work_archive": archive_record,
        "source": {
            "package_count": 2,
            "base": source["base"],
            "update": source["update"],
            "base_drive": base_record,
            "update_drive": update_record,
            "rar_parts_deleted_after_upload": True,
            "base_rar_volume_count": source.get("base_rar_volume_count"),
            "update_download_kind": source.get("update_download_kind"),
            "dlc_package_count": len(source.get("dlc_drive_items", [])),
            "dlc_packages": source.get("dlc_drive_items", []),
            "dlc_inventory": source.get("dlc_inventory", {}),
        },
        "game_data": {
            "folder_id": game_id,
            "folder_url": f"https://drive.google.com/drive/folders/{game_id}",
            "base_package": base_record,
            "update_package": update_record,
            "romfs": romfs_record,
            "romfs_relative_path": prep["romfs_relative_path"],
            "romfs_id_relative_path": prep["romfs_id_relative_path"],
            "aoc_folder_id": aoc_id,
            "aoc_folder_url": f"https://drive.google.com/drive/folders/{aoc_id}",
            "aoc_count": len(aoc_records),
            "aoc": aoc_records,
            "aoc_relative_dir": prep.get("aoc_relative_dir", "aoc"),
        },
        "prepared": prep,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    handoff_path = ROOT / "handoff.json"
    handoff_path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    handoff_record = upsert_drive_file(api, handoff_path, output_id, "handoff.json")
    print("\n[KaKaRoTiOS] Three-volume BASE reconstruction + direct UPDATE NSP download, Drive uploads and Colab preparation completed.", flush=True)
    print("Request:", request_id)
    print("Drive:", handoff["drive_output_folder_url"])
    print("Base package:", base_record["name"], f"{base_record['size']:,} bytes; SHA-256 {base_record['sha256']}")
    print("Update package:", update_record["name"], f"{update_record['size']:,} bytes; SHA-256 {update_record['sha256']}")
    print("BASE RAR parts: deleted after both package uploads were verified on Drive; UPDATE was one direct NSP.")
    print("RomFS:", f"{romfs_record['size']:,} bytes; SHA-256 {romfs_record['sha256']}")
    print("AOC images:", len(aoc_records), "(zero is expected unless DLC content was supplied)")
    print("Workspace:", f"{archive_record['size']:,} bytes; SHA-256 {archive_record['sha256']}")
    print("Handoff Drive ID:", handoff_record["id"])
    print("Dispatch remains a separate, explicit notebook cell targeting KaKaRoTiOS only.")
    return handoff

def recover(args, api=None) -> dict | None:
    api = api or drive_api()
    configured_root_items = list_children(api, args.drive_folder_id)
    kakarot_folders = [x for x in configured_root_items
                       if x.get("mimeType") == FOLDER_MIME
                       and x.get("name", "").lower() == "kakarot"]
    if len(kakarot_folders) != 1:
        fail(f"Expected exactly one 'kakarot' folder under the configured Drive root during recovery; found {len(kakarot_folders)}.")
    folders = [x for x in list_children(api, kakarot_folders[0]["id"])
               if x.get("mimeType") == FOLDER_MIME and x.get("name", "").startswith("KaKaRoTiOS_")]
    folders.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)
    for folder in folders:
        manifest = next((x for x in list_children(api, folder["id"])
                         if x.get("mimeType") != FOLDER_MIME and x.get("name", "").lower() == "handoff.json"), None)
        if not manifest:
            continue
        local = ROOT / "handoff.json"
        try:
            download_drive_file(api, manifest, local)
            handoff = json.loads(local.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[KaKaRoTiOS] Skipping incomplete Drive run {folder['name']}: {exc}", flush=True)
            continue
        prepared = handoff.get("prepared") or {}
        source = handoff.get("source") or {}
        scanned = prepared.get("input_packages", [])
        scanned_dlcs = [item for item in scanned if str(item.get("name", "")).startswith("dlc_")]
        source_dlcs = source.get("dlc_packages", [])
        if (handoff.get("project") == PROJECT and handoff.get("branch") == BRANCH
                and handoff.get("title_id") == TITLE_ID
                and handoff.get("nx2apple_tag") == NX2APPLE_TAG
                and handoff.get("engine_pin") == ENGINE_PIN
                and handoff.get("package_version") == prepared.get("package_version")
                and handoff.get("work_archive", {}).get("id")
                and handoff.get("game_data", {}).get("base_package", {}).get("id")
                and handoff.get("game_data", {}).get("update_package", {}).get("id")
                and handoff.get("game_data", {}).get("romfs", {}).get("id")
                and handoff.get("game_data", {}).get("aoc_folder_id")
                and int(handoff.get("game_data", {}).get("aoc_count", -1)) == len(handoff.get("game_data", {}).get("aoc", []))
                and source.get("package_count") == 2
                and source.get("base", {}).get("archive", {}).get("source_kind") == "three_volume_rar"
                and len(source.get("base", {}).get("archive", {}).get("rar_volumes", [])) == 3
                and source.get("update_download_kind") == "direct_nsp"
                and source.get("update", {}).get("type") == "NSP"
                and source.get("update", {}).get("archive", {}).get("source_kind") == "direct_nsp_download"
                and source.get("dlc_package_count") == 20 and len(source_dlcs) == 20
                and prepared.get("input_package_count") == 22 and len(scanned) == 22
                and prepared.get("input_dlc_package_count") == 20 and len(scanned_dlcs) == 20
                and prepared.get("profile_type") == "provisional"
                and prepared.get("graphics_api") == "nvn"):
            print("[KaKaRoTiOS] Verified handoff recovered from Drive; package download, extraction and rewrite need not be repeated.")
            print("Request:", handoff["request_id"])
            print("Drive:", handoff.get("drive_output_folder_url"))
            print("Package:", handoff["package_version"])
            print("Local manifest:", local)
            return handoff
    print("[KaKaRoTiOS] No completed KaKaRoTiOS handoff was found in Drive.")
    return None

def dispatch(args) -> None:
    import requests
    handoff_path = args.handoff.resolve()
    if not handoff_path.is_file():
        fail(f"Handoff manifest not found: {handoff_path}")
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if (handoff.get("project") != PROJECT or handoff.get("branch") != BRANCH
            or handoff.get("title_id") != TITLE_ID
            or handoff.get("nx2apple_tag") != NX2APPLE_TAG
            or handoff.get("engine_pin") != ENGINE_PIN):
        fail("Refusing to dispatch a handoff that does not belong to KaKaRoTiOS/Kakarot.")
    prepared = handoff.get("prepared") or {}
    source = handoff.get("source") or {}
    scanned = prepared.get("input_packages", [])
    scanned_dlcs = [item for item in scanned if str(item.get("name", "")).startswith("dlc_")]
    source_dlcs = source.get("dlc_packages", [])
    if (prepared.get("profile_type") != "provisional" or prepared.get("graphics_api") != "nvn"
            or source.get("package_count") != 2
            or source.get("base", {}).get("archive", {}).get("source_kind") != "three_volume_rar"
            or len(source.get("base", {}).get("archive", {}).get("rar_volumes", [])) != 3
            or source.get("update_download_kind") != "direct_nsp"
            or source.get("update", {}).get("type") != "NSP"
            or source.get("update", {}).get("archive", {}).get("source_kind") != "direct_nsp_download"
            or source.get("dlc_package_count") != 20 or len(source_dlcs) != 20
            or prepared.get("input_package_count") != 22 or len(scanned) != 22
            or prepared.get("input_dlc_package_count") != 20 or len(scanned_dlcs) != 20):
        fail("Refusing dispatch: handoff must contain base + update + exactly 20 DLCs (22 NXNative inputs).")
    token = getpass.getpass("Fine-grained GitHub token (KintTany repository, Contents: Read and write): ").strip()
    if not token:
        fail("GitHub token is empty.")
    api = f"https://api.github.com/repos/{REPO}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    branch_check = requests.get(f"{api}/branches/{quote(BRANCH, safe='')}", headers=headers, timeout=30)
    if branch_check.status_code != 200:
        fail(f"Cannot verify target branch {BRANCH} ({branch_check.status_code}): {branch_check.text[:1000]}")
    if branch_check.json().get("name") != BRANCH:
        fail("GitHub branch response does not match KaKaRoTiOS.")
    url = f"{api}/contents/handoff.json"
    existing = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=30)
    if existing.status_code not in (200, 404):
        fail(f"Cannot read {BRANCH}/handoff.json ({existing.status_code}): {existing.text[:1000]}")
    body = {
        "message": f"Queue KaKaRoTiOS build {handoff['request_id'][:8]}",
        "content": base64.b64encode((json.dumps(handoff, indent=2) + "\n").encode()).decode(),
        "branch": BRANCH,
    }
    if existing.status_code == 200:
        body["sha"] = existing.json()["sha"]
    response = requests.put(url, headers=headers, json=body, timeout=60)
    if response.status_code not in (200, 201):
        fail(f"GitHub rejected the KaKaRoTiOS handoff commit ({response.status_code}): {response.text[:1500]}")
    print("[KaKaRoTiOS] Handoff committed to KaKaRoTiOS only.")
    print("Commit:", response.json().get("commit", {}).get("html_url", ""))
    print("No workflow on SpkIOSzero, Link2iOS or any other branch was targeted.")
    print("The token was used in memory only; it was not written to Drive or the repository.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Kakarot isolated Colab RAR multipart pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="download three BASE RAR volumes plus one direct UPDATE NSP")
    p.add_argument("--drive-folder-id", required=True)
    p.add_argument("--base-part-urls", nargs=3, required=True)
    p.add_argument("--update-package-url", required=True)
    p.add_argument("--base-part-names", nargs=3, default=["", "", ""])
    p.set_defaults(func=prepare)
    p = sub.add_parser("recover", help="recover the latest valid KaKaRoTiOS handoff from Drive")
    p.add_argument("--drive-folder-id", required=True)
    p.set_defaults(func=recover)
    p = sub.add_parser("dispatch", help="commit the handoff to KaKaRoTiOS and queue only its branch workflow")
    p.add_argument("--handoff", type=Path, default=ROOT / "handoff.json")
    p.set_defaults(func=dispatch)
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
