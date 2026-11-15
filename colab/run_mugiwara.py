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
BRANCH = "Mugiwara4iOS"
PROJECT = "Mugiwara4iOS"
TITLE_ID = "01008FE00E2F6000"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
CHUNK = 64 * 1024 * 1024
FOLDER_MIME = "application/vnd.google-apps.folder"
ROOT = Path("/content/mugi")

def fail(message: str) -> None:
    raise SystemExit("[Mugiwara4iOS] ERROR: " + message)

def valid_aoc_manifest(prep: dict, drive_records: list[dict] | None = None) -> bool:
    """Validate one external AOC per unique DLC Title ID, not one per source NSP."""
    try:
        count = prep.get("aoc_count")
        title_ids = prep.get("aoc_title_ids")
        contents = prep.get("aoc_contents")
        images = prep.get("aoc_images")
        dlc_meta = prep.get("dlc_content_meta")
        packages = prep.get("input_packages")
        if type(count) is not int or not 1 <= count <= 44:
            return False
        if not all(isinstance(x, list) for x in (title_ids, contents, images, dlc_meta, packages)):
            return False
        if (len(title_ids) != count or len(set(title_ids)) != count
                or len(contents) != count or len(images) != count
                or len(dlc_meta) < 44 or prep.get("dlc_content_meta_count") != len(dlc_meta)):
            return False
        app = int(TITLE_ID, 16)
        dlc_packages = {
            item.get("local_name"): item for item in packages
            if item.get("role") == "dlc" and item.get("type") == "NSP"
        }
        if len(dlc_packages) != 44:
            return False
        best = {}
        for item in dlc_meta:
            tid_text = item.get("title_id", "")
            if (not isinstance(tid_text, str) or len(tid_text) != 16
                    or f"{int(tid_text, 16):016X}" != tid_text
                    or item.get("source_package") not in dlc_packages):
                return False
            tid = int(tid_text, 16)
            version = int(item.get("content_version", -1))
            package = dlc_packages[item["source_package"]]
            key = (version, int(package.get("size", 0)))
            if version < 0 or key[1] <= 0:
                return False
            if tid not in best or key > best[tid][0]:
                best[tid] = (key, item["source_package"], version)
        if set(title_ids) != {f"{tid:016X}" for tid in best}:
            return False
        if {item.get("source_package") for item in dlc_meta} != set(dlc_packages):
            return False
        content_by_title = {item.get("title_id"): item for item in contents}
        if len(content_by_title) != count or set(content_by_title) != set(title_ids):
            return False
        expected_names = set()
        for tid in sorted(best):
            title = f"{tid:016X}"
            index = tid - app - 0x1000
            name = f"{index}.img"
            expected_names.add(name)
            item = content_by_title[title]
            selected_package = dlc_packages[best[tid][1]]
            if (index <= 0 or item.get("aoc_index") != index or item.get("name") != name
                    or item.get("content_version") != best[tid][2]
                    or item.get("source_package") != best[tid][1]
                    or item.get("source_size") != int(selected_package.get("size", 0))
                    or item.get("source_sha256") != selected_package.get("sha256")):
                return False
        image_by_name = {item.get("name"): item for item in images}
        if len(image_by_name) != count or set(image_by_name) != expected_names:
            return False
        for title, content in content_by_title.items():
            image = image_by_name[content["name"]]
            digest = image.get("sha256", "")
            if (image.get("title_id") != title or image.get("aoc_index") != content["aoc_index"]
                    or int(image.get("size", 0)) <= 0 or len(digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in digest.lower())):
                return False
        if drive_records is not None:
            drive_by_name = {item.get("name"): item for item in drive_records}
            if len(drive_by_name) != count or set(drive_by_name) != expected_names:
                return False
            for name, image in image_by_name.items():
                record = drive_by_name[name]
                if (not record.get("id") or record.get("title_id") != image.get("title_id")
                        or record.get("aoc_index") != image.get("aoc_index")
                        or int(record.get("size", 0)) != int(image.get("size", -1))
                        or record.get("sha256") != image.get("sha256")):
                    return False
        return True
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return False


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

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    size = path.stat().st_size
    if size <= 0:
        fail(f"Refusing to upload empty file {name}.")
    print(f"[Mugiwara4iOS] Uploading {name}: {size:,} bytes ({size/2**30:.2f} GiB)...", flush=True)
    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            chunksize=CHUNK, resumable=True)
    request = api.files().create(
        body={"name": name, "parents": [parent_id]}, media_body=media,
        fields="id,name,size", supportsAllDrives=True)
    item = None
    while item is None:
        status, item = request.next_chunk()
        if status:
            print(f"[Mugiwara4iOS] Drive upload {name}: {status.progress()*100:.1f}%", flush=True)
    if int(item.get("size", -1)) != size:
        fail(f"Drive upload size mismatch for {name}.")
    digest = sha256_file(path)
    record = {"id": item["id"], "name": item["name"], "size": size, "sha256": digest}
    print(f"[Mugiwara4iOS] Upload verified: {name}; SHA-256 {digest}.", flush=True)
    return record

def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    from http.client import IncompleteRead
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
            except (IncompleteRead, TimeoutError, ConnectionError, OSError) as exc:
                retries += 1
                if retries > 10:
                    raise RuntimeError(f"Drive download failed after {retries-1} retries: {exc}") from exc
                delay = min(2 ** min(retries, 5), 30)
                print(f"[Mugiwara4iOS] Drive transfer interrupted at {downloader._progress}; retry {retries}/10 in {delay}s.", flush=True)
                time.sleep(delay)
                continue
            if status:
                print(f"[Mugiwara4iOS] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
    size = part.stat().st_size
    expected_size = int(item.get("size", -1))
    if size <= 0 or size != expected_size:
        part.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item.get('name')}: received {size}, expected {expected_size}.")
    expected_sha = str(item.get("sha256", "")).lower()
    if expected_sha:
        digest = sha256_file(part)
        if digest.lower() != expected_sha:
            part.unlink(missing_ok=True)
            fail(f"Drive SHA-256 mismatch for {item.get('name')}.")
    expected_md5 = str(item.get("md5Checksum", "")).lower()
    if expected_md5:
        md5 = hashlib.md5()
        with part.open("rb") as stream:
            for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
                md5.update(block)
        if md5.hexdigest().lower() != expected_md5:
            part.unlink(missing_ok=True)
            fail(f"Drive MD5 mismatch for {item.get('name')}.")
    part.replace(destination)


def build_work_archive(work: Path, destination: Path) -> None:
    """Archive only reproducible workspace outputs; RomFS is stored as a separate Drive object."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "tar", "-C", str(work),
        "--exclude=./tools", "--exclude=./tmp",
        "--exclude=./extract/*/RomFS.img", "--exclude=*/RomFS.img",
        "--exclude=./aoc/*.img", "--exclude=*/aoc/*.img",
        "--exclude=./extract/*/RomFS.img.part",
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
        print(f"[Mugiwara4iOS] Cloning NX2Apple {NX2APPLE_TAG}; syncing the exact NXNative pin {ENGINE_PIN}...", flush=True)
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
    from source_mugiwara import prepare_source
    source = prepare_source(api, args.drive_folder_id, ROOT,
        args.base_url, args.update_url, args.base_filename, args.update_filename)
    if (source.get("package_count") != 46 or source.get("update_nsp_count") != 1
            or source.get("dlc_nsp_count") != 44 or source.get("base_type") != "NSP"):
        fail("Drive/mugi source contract failed: expected 1 base NSP + 1 update NSP + 44 arbitrarily named DLC NSPs.")
    input_dir, keys = Path(source["package_dir"]), Path(source["keys_path"])
    print("[Mugiwara4iOS] Source inventory verified: 1 base + 1 update + 44 DLCs in Drive/mugi.", flush=True)

    nx = install_nx2apple(ROOT)
    work = ROOT / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    from prepare_mugiwara import run_preparation
    prep = run_preparation(argparse.Namespace(
        nx2apple_root=nx, package_dir=input_dir, keys=keys, work_dir=work,
        source_manifest=Path(source["manifest_path"])))
    if prep.get("project") != PROJECT or prep.get("title_id") != TITLE_ID:
        fail("NXNative preparation manifest does not belong to Mugiwara4iOS/One Piece: Pirate Warriors 4.")
    if prep.get("nx2apple_tag") != NX2APPLE_TAG or prep.get("engine_pin") != ENGINE_PIN:
        fail("Preparation manifest uses another NX2Apple/NXNative pin.")
    if (prep.get("format") != 4 or prep.get("display_version") != "1.8.7"
            or prep.get("base_content_version") != 0 or int(prep.get("update_content_version", 0)) <= 0
            or prep.get("input_package_count") != 46
            or prep.get("input_dlc_nsp_count") != 44 or prep.get("input_update_nsp_count") != 1
            or not valid_aoc_manifest(prep)):
        fail("NXNative preparation contract failed: expected 46 source NSPs (1 base + 1 update + 44 DLCs) and one AOC per unique DLC Title ID.")
    if prep.get("package_version") == "v0":
        fail("The update NSP was not selected; refusing a base-only build.")

    def relative_file(key: str) -> Path:
        rel = Path(prep[key])
        if rel.is_absolute() or ".." in rel.parts:
            fail(f"Unsafe {key} path in the preparation manifest: {rel}")
        return work.joinpath(*rel.parts)

    romfs = relative_file("romfs_relative_path")
    romfs_id = relative_file("romfs_id_relative_path")
    aoc_dir = relative_file("aoc_relative_dir")
    aoc_files = sorted(p for p in aoc_dir.glob("*.img") if p.is_file())
    expected_aoc = {x["name"] for x in prep.get("aoc_images", [])}
    if not romfs.is_file() or romfs.stat().st_size != int(prep["romfs_size"]):
        fail("Prepared external RomFS is missing or has the wrong size.")
    if sha256_file(romfs) != prep["romfs_sha256"]:
        fail("Prepared RomFS SHA-256 differs from the Linux preparation manifest.")
    if not romfs_id.is_file():
        fail("NXNative RomFS identity sidecar is missing.")
    identity = json.loads(romfs_id.read_text(encoding="utf-8"))
    if (identity.get("title") != TITLE_ID.lower()
            or identity.get("version") != prep["package_version"]
            or identity.get("bytes") != prep["romfs_size"]
            or identity.get("sha256") != prep["romfs_sha256"]):
        fail("RomFS identity sidecar does not match the game/version/size/SHA-256.")
    if len(aoc_files) != prep["aoc_count"] or {p.name for p in aoc_files} != expected_aoc:
        fail(f"Prepared AOC files differ from the NXNative manifest: {len(aoc_files)} files, expected {prep['aoc_count']} unique-title-ID images.")

    request_id = str(uuid.uuid4())
    # Every persistent build output/checkpoint is inside the user's existing Drive/mugi folder.
    output_id = create_folder(api, f"Mugiwara4iOS_{request_id[:8]}", source["source_folder_id"])
    pipeline_id = create_folder(api, "pipeline", output_id)
    games_id = create_folder(api, "games", output_id)
    game_id = create_folder(api, TITLE_ID.lower(), games_id)
    aoc_id = create_folder(api, "aoc", game_id)
    print(f"[Mugiwara4iOS] Uploading external RomFS and {len(aoc_files)} unique-title-ID AOC images "
          "under Drive/mugi/Mugiwara4iOS_*/games/...", flush=True)
    romfs_record = upload_drive_file(api, romfs, game_id, "romfs.img")
    aoc_by_name = {item["name"]: item for item in prep["aoc_images"]}
    aoc_records = []
    for image in aoc_files:
        record = upload_drive_file(api, image, aoc_id, image.name)
        meta = aoc_by_name[image.name]
        record["role"] = "aoc"
        record["title_id"] = meta["title_id"]
        record["aoc_index"] = meta["aoc_index"]
        aoc_records.append(record)

    archive = ROOT / "mugiwara4ios-work.tar.zst"
    print(f"[Mugiwara4iOS] Archiving workspace only; excluding 46 source NSPs, prod.keys, RomFS.img and {len(aoc_files)} AOC images.", flush=True)
    build_work_archive(work, archive)
    archive_record = upload_drive_file(api, archive, pipeline_id, "mugiwara4ios-work.tar.zst")

    handoff = {
        "format": 2, "project": PROJECT, "branch": BRANCH, "request_id": request_id,
        "title_id": TITLE_ID, "package_version": prep["package_version"],
        "nx2apple_tag": NX2APPLE_TAG, "engine_pin": ENGINE_PIN,
        "drive_source_folder_id": source["source_folder_id"],
        "drive_source_folder_name": source["source_folder_name"],
        "drive_output_folder_id": output_id,
        "drive_output_folder_url": f"https://drive.google.com/drive/folders/{output_id}",
        "work_archive": archive_record,
        "source": {
            "folder_name": source["source_folder_name"],
            "package_count": 46, "base_type": "NSP", "base_extension": ".nsp",
            "base_file_name": source["base_file_name"],
            "update_file_name": source["update_file_name"],
            "input_nsp_count": 46, "input_xci_count": 0,
            "update_nsp_count": 1, "dlc_nsp_count": 44,
            "base": {k: source["base"][k] for k in ("name", "drive_name", "size", "sha256", "source", "url_sha256")},
            "update": {k: source["update"][k] for k in ("name", "drive_name", "size", "sha256", "source", "url_sha256")},
            "dlc_files": source["dlc_files"],
        },
        "game_data": {
            "folder_id": game_id,
            "folder_url": f"https://drive.google.com/drive/folders/{game_id}",
            "romfs": romfs_record, "aoc": aoc_records,
            "romfs_relative_path": prep["romfs_relative_path"],
            "romfs_id_relative_path": prep["romfs_id_relative_path"],
            "aoc_relative_dir": prep["aoc_relative_dir"],
            "aoc_count": prep["aoc_count"], "aoc_title_ids": prep["aoc_title_ids"],
        },
        "prepared": prep,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    handoff_path = ROOT / "handoff.json"
    handoff_path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    handoff_record = upload_drive_file(api, handoff_path, output_id, "handoff.json")
    print("\\n[Mugiwara4iOS] Colab/Linux preparation and Drive checkpoints completed.", flush=True)
    print("Request:", request_id)
    print("Drive/mugi checkpoint:", handoff["drive_output_folder_url"])
    print("Base:", source["base"]["size"], "bytes; SHA-256", source["base"]["sha256"])
    print("Update:", source["update"]["size"], "bytes; SHA-256", source["update"]["sha256"])
    print("DLC NSPs:", source["dlc_nsp_count"], "· AOC images:", len(aoc_records))
    print("RomFS:", f'{romfs_record["size"]:,} bytes; SHA-256 {romfs_record["sha256"]}')
    print("Workspace:", f'{archive_record["size"]:,} bytes; SHA-256 {archive_record["sha256"]}')
    print("Handoff Drive ID:", handoff_record["id"])
    print("Dispatch remains a separate, explicit last notebook cell; no Actions run was started here.")
    return handoff

def recover(args, api=None) -> dict | None:
    api = api or drive_api()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from source_mugiwara import source_folder
    mugi_folder, _ = source_folder(api, args.drive_folder_id)
    folders = [x for x in list_children(api, mugi_folder["id"])
               if x.get("mimeType") == FOLDER_MIME and x.get("name", "").startswith("Mugiwara4iOS_")]
    folders.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    for folder in folders:
        manifest = next((x for x in list_children(api, folder["id"])
                         if x.get("mimeType") != FOLDER_MIME and x.get("name", "").casefold() == "handoff.json"), None)
        if not manifest:
            continue
        local = ROOT / "handoff.json"
        try:
            download_drive_file(api, manifest, local)
            handoff = json.loads(local.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[Mugiwara4iOS] Skipping incomplete Drive/mugi run {folder['name']}: {exc}", flush=True)
            continue
        prepared = handoff.get("prepared") or {}
        source = handoff.get("source") or {}
        aoc = (handoff.get("game_data") or {}).get("aoc") or []
        if (handoff.get("format") == 2 and handoff.get("project") == PROJECT
                and handoff.get("branch") == BRANCH and handoff.get("title_id") == TITLE_ID
                and handoff.get("nx2apple_tag") == NX2APPLE_TAG and handoff.get("engine_pin") == ENGINE_PIN
                and handoff.get("package_version") == prepared.get("package_version")
                and prepared.get("display_version") == "1.8.7"
                and prepared.get("base_content_version") == 0
                and int(prepared.get("update_content_version", 0)) > 0
                and handoff.get("drive_source_folder_id") == mugi_folder["id"]
                and handoff.get("work_archive", {}).get("id")
                and (handoff.get("game_data") or {}).get("romfs", {}).get("id")
                and prepared.get("format") == 4 and isinstance(prepared.get("jit_required"), bool)
                and prepared.get("profile_type") == "provisional" and prepared.get("graphics_api") == "nvn"
                and source.get("package_count") == 46 and source.get("base_type") == "NSP"
                and source.get("update_nsp_count") == 1 and source.get("dlc_nsp_count") == 44
                and prepared.get("input_package_count") == 46 and prepared.get("input_nsp_count") == 46
                and prepared.get("input_xci_count") == 0 and prepared.get("input_update_nsp_count") == 1
                and prepared.get("input_dlc_nsp_count") == 44
                and valid_aoc_manifest(prepared, aoc)):
            print("[Mugiwara4iOS] Valid 46-package/44-DLC-NSP handoff with unique-title-ID AOC set recovered from Drive/mugi; no NSP download, extraction or rewrite repeated.")
            print("Request:", handoff["request_id"])
            print("Drive:", handoff.get("drive_output_folder_url"))
            print("Package:", handoff["package_version"])
            print("DLC NSPs / AOC images:", source["dlc_nsp_count"], "/", len(aoc))
            print("nn::jit static AOT required:", prepared["jit_required"])
            print("Local manifest:", local)
            return handoff
        local.unlink(missing_ok=True)
    print("[Mugiwara4iOS] No completed Mugiwara4iOS handoff found inside Drive/mugi.")
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
        fail("Refusing to dispatch a handoff that does not belong to Mugiwara4iOS/One Piece: Pirate Warriors 4.")
    prepared = handoff.get("prepared") or {}
    source = handoff.get("source") or {}
    aoc = (handoff.get("game_data") or {}).get("aoc") or []
    if (handoff.get("format") != 2 or prepared.get("format") != 4
            or not isinstance(prepared.get("jit_required"), bool)
            or prepared.get("profile_type") != "provisional" or prepared.get("graphics_api") != "nvn"
            or prepared.get("display_version") != "1.8.7" or prepared.get("base_content_version") != 0
            or int(prepared.get("update_content_version", 0)) <= 0
            or source.get("package_count") != 46 or source.get("base_type") != "NSP"
            or source.get("update_nsp_count") != 1 or source.get("dlc_nsp_count") != 44
            or prepared.get("input_package_count") != 46 or prepared.get("input_nsp_count") != 46
            or prepared.get("input_xci_count") != 0 or prepared.get("input_update_nsp_count") != 1
            or prepared.get("input_dlc_nsp_count") != 44
            or not valid_aoc_manifest(prepared, aoc)):
        fail("Refusing dispatch: expected 1 base + 1 update + 44 DLC NSPs, one AOC image per unique DLC Title ID and the generated provisional NVN profile.")
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
        fail("GitHub branch response does not match Mugiwara4iOS.")
    url = f"{api}/contents/handoff.json"
    existing = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=30)
    if existing.status_code not in (200, 404):
        fail(f"Cannot read {BRANCH}/handoff.json ({existing.status_code}): {existing.text[:1000]}")
    body = {
        "message": f"Queue Mugiwara4iOS build {handoff['request_id'][:8]}",
        "content": base64.b64encode((json.dumps(handoff, indent=2) + "\n").encode()).decode(),
        "branch": BRANCH,
    }
    if existing.status_code == 200:
        body["sha"] = existing.json()["sha"]
    response = requests.put(url, headers=headers, json=body, timeout=60)
    if response.status_code not in (200, 201):
        fail(f"GitHub rejected the Mugiwara4iOS handoff commit ({response.status_code}): {response.text[:1500]}")
    print("[Mugiwara4iOS] Handoff committed to Mugiwara4iOS only.")
    print("Commit:", response.json().get("commit", {}).get("html_url", ""))
    print("No workflow on SpkIOSzero, Link2iOS or any other branch was targeted.")
    print("The token was used in memory only; it was not written to Drive or the repository.")

def main() -> None:
    parser = argparse.ArgumentParser(description="One Piece: Pirate Warriors 4 isolated Colab pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="download base/update, generate One Piece: Pirate Warriors 4 profile/rewrite, upload separate RomFS + workspace")
    p.add_argument("--drive-folder-id", required=True)
    p.add_argument("--base-url", default=os.environ.get("MUGIWARA4IOS_BASE_URL", ""))
    p.add_argument("--update-url", default=os.environ.get("MUGIWARA4IOS_UPDATE_URL", ""))
    p.add_argument("--base-filename", default=os.environ.get("MUGIWARA4IOS_BASE_FILENAME", "Mugiwara4iOS_BASE_v0.nsp"))
    p.add_argument("--update-filename", default=os.environ.get("MUGIWARA4IOS_UPDATE_FILENAME", "Mugiwara4iOS_UPDATE_v1.8.7.nsp"))
    p.set_defaults(func=prepare)
    p = sub.add_parser("recover", help="recover the latest valid Mugiwara4iOS handoff from Drive")
    p.add_argument("--drive-folder-id", required=True)
    p.set_defaults(func=recover)
    p = sub.add_parser("dispatch", help="commit the handoff to Mugiwara4iOS and thereby queue only its branch workflow")
    p.add_argument("--handoff", type=Path, default=ROOT / "handoff.json")
    p.set_defaults(func=dispatch)
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
