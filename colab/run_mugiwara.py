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
ROOT = Path("/content/mugiwara4ios")

def fail(message: str) -> None:
    raise SystemExit("[Mugiwara4iOS] ERROR: " + message)

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
                print(f"[Mugiwara4iOS] Drive transfer interrupted at {downloader._progress}; retry {retries}/10 in {delay}s.", flush=True)
                time.sleep(delay)
                continue
            if status:
                print(f"[Mugiwara4iOS] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
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
    input_dir, keys = Path(source["package_dir"]), Path(source["keys_path"])
    print(
        f"[Mugiwara4iOS] Source verified: base {source['base']['type']} ({source['base']['name']}) "
        f"+ update {source['update']['type']} ({source['update']['name']}).",
        flush=True)
    nx = install_nx2apple(ROOT)
    work = ROOT / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    from prepare_mugiwara import run_preparation
    prep = run_preparation(argparse.Namespace(
        nx2apple_root=nx, package_dir=input_dir, keys=keys, work_dir=work))
    if prep.get("project") != PROJECT or prep.get("title_id") != TITLE_ID:
        fail("NXNative preparation manifest does not belong to Mugiwara4iOS/One Piece: Pirate Warriors 4.")
    if prep.get("nx2apple_tag") != NX2APPLE_TAG or prep.get("engine_pin") != ENGINE_PIN:
        fail("Preparation manifest uses another NX2Apple/NXNative pin.")
    if prep.get("package_version") == "v0":
        print("[Mugiwara4iOS] NOTE: selected package is base v0; confirm update content metadata was recognized.", flush=True)

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

    request_id = str(uuid.uuid4())
    output_id = create_folder(api, f"Mugiwara4iOS_{request_id[:8]}", args.drive_folder_id)
    pipeline_id = create_folder(api, "pipeline", output_id)
    games_id = create_folder(api, "games", output_id)
    game_id = create_folder(api, TITLE_ID.lower(), games_id)
    print("[Mugiwara4iOS] Uploading external RomFS separately from the build workspace...", flush=True)
    romfs_record = upload_drive_file(api, romfs, game_id, "romfs.img")
    archive = ROOT / "mugiwara4ios-work.tar.zst"
    print("[Mugiwara4iOS] Archiving rewritten ExeFS, ARM64 rewrite audits, generated profile and survey; excluding source NSP/XCI, prod.keys and RomFS.", flush=True)
    build_work_archive(work, archive)
    archive_record = upload_drive_file(api, archive, pipeline_id, "mugiwara4ios-work.tar.zst")

    handoff = {
        "format": 1,
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
            "base": {k: source["base"][k] for k in ("name", "type", "size", "sha256", "url_sha256")},
            "update": {k: source["update"][k] for k in ("name", "type", "size", "sha256", "url_sha256")},
            "input_nsp_count": source["input_nsp_count"],
            "input_xci_count": source["input_xci_count"],
        },
        "game_data": {
            "folder_id": game_id,
            "folder_url": f"https://drive.google.com/drive/folders/{game_id}",
            "romfs": romfs_record,
            "romfs_relative_path": prep["romfs_relative_path"],
            "romfs_id_relative_path": prep["romfs_id_relative_path"],
        },
        "prepared": prep,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    handoff_path = ROOT / "handoff.json"
    handoff_path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    handoff_record = upload_drive_file(api, handoff_path, output_id, "handoff.json")
    print("\n[Mugiwara4iOS] Linux preparation and Drive checkpoints completed.", flush=True)
    print("Request:", request_id)
    print("Drive:", handoff["drive_output_folder_url"])
    print("Base:", source["base"]["type"], f"{source['base']['size']:,} bytes; SHA-256 {source['base']['sha256']}")
    print("Update:", source["update"]["type"], f"{source['update']['size']:,} bytes; SHA-256 {source['update']['sha256']}")
    print("RomFS:", f"{romfs_record['size']:,} bytes; SHA-256 {romfs_record['sha256']}")
    print("Workspace:", f"{archive_record['size']:,} bytes; SHA-256 {archive_record['sha256']}")
    print("Handoff Drive ID:", handoff_record["id"])
    print("Dispatch is a separate, explicit notebook cell. It writes handoff.json to Mugiwara4iOS only.")
    return handoff

def recover(args, api=None) -> dict | None:
    api = api or drive_api()
    folders = [x for x in list_children(api, args.drive_folder_id)
               if x.get("mimeType") == FOLDER_MIME and x.get("name", "").startswith("Mugiwara4iOS_")]
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
            print(f"[Mugiwara4iOS] Skipping incomplete Drive run {folder['name']}: {exc}", flush=True)
            continue
        prepared = handoff.get("prepared") or {}
        if (handoff.get("project") == PROJECT and handoff.get("branch") == BRANCH
                and handoff.get("title_id") == TITLE_ID
                and handoff.get("nx2apple_tag") == NX2APPLE_TAG
                and handoff.get("engine_pin") == ENGINE_PIN
                and handoff.get("package_version") == prepared.get("package_version")
                and handoff.get("work_archive", {}).get("id")
                and handoff.get("game_data", {}).get("romfs", {}).get("id")
                and prepared.get("format") == 2
                and isinstance(prepared.get("jit_required"), bool)
                and prepared.get("profile_type") == "provisional"
                and prepared.get("graphics_api") == "nvn"):
            print("[Mugiwara4iOS] Verified handoff recovered from Drive; package download, extraction and rewrite need not be repeated.")
            print("Request:", handoff["request_id"])
            print("Drive:", handoff.get("drive_output_folder_url"))
            print("Package:", handoff["package_version"])
            print("nn::jit static AOT required:", prepared["jit_required"])
            print("Local manifest:", local)
            return handoff
    print("[Mugiwara4iOS] No completed Mugiwara4iOS handoff was found in Drive.")
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
    if (prepared.get("format") != 2 or not isinstance(prepared.get("jit_required"), bool)
            or prepared.get("profile_type") != "provisional" or prepared.get("graphics_api") != "nvn"):
        fail("Refusing dispatch: expected the One Piece: Pirate Warriors 4 provisional NVN profile.")
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
    p.add_argument("--base-filename", default=os.environ.get("MUGIWARA4IOS_BASE_FILENAME", "base.nsp"))
    p.add_argument("--update-filename", default=os.environ.get("MUGIWARA4IOS_UPDATE_FILENAME", "update.nsp"))
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
