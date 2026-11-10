#!/usr/bin/env python3
"""Google Drive -> Colab/Linux -> Drive -> Link2iOS GitHub handoff."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "Link2iOS"
TITLE_ID = "01007EF00011E000"
PACKAGE_VERSION = "v1114112"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
CHUNK = 64 * 1024 * 1024


def fail(message: str) -> None:
    raise SystemExit("[Link2iOS] ERROR: " + message)


def service_account_json() -> dict:
    raw = os.environ.get("LINK2IOS_GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        try:
            from google.colab import userdata
            raw = userdata.get("LINK2IOS_GOOGLE_SERVICE_ACCOUNT_JSON") or ""
        except Exception:
            raw = ""
    if not raw:
        fail("configure the Colab Secret LINK2IOS_GOOGLE_SERVICE_ACCOUNT_JSON.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"service-account JSON is invalid: {exc}")


def drive_api():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    credentials = service_account.Credentials.from_service_account_info(
        service_account_json(),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def list_children(api, parent_id: str) -> list[dict]:
    items, token = [], None
    while True:
        result = api.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000,
            pageToken=token,
            orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        items.extend(result.get("files", []))
        token = result.get("nextPageToken")
        if not token:
            return items


def by_name(items: list[dict], *names: str) -> dict | None:
    wanted = {name.lower() for name in names}
    return next((item for item in items if item.get("name", "").lower() in wanted), None)


def create_folder(api, name: str, parent_id: str) -> str:
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    result = api.files().create(
        body=body, fields="id,name", supportsAllDrives=True
    ).execute()
    return result["id"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_drive_file(api, item: dict, destination: Path) -> dict:
    from googleapiclient.http import MediaIoBaseDownload
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    digest, total = hashlib.sha256(), 0
    with temp.open("wb") as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=CHUNK)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"  {item['name']}: {status.progress() * 100:.1f}%", flush=True)
    with temp.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
            total += len(block)
    expected = int(item.get("size") or 0)
    if expected and total != expected:
        temp.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item['name']}: expected {expected}, got {total}")
    temp.replace(destination)
    return {"name": item["name"], "id": item["id"], "size": total, "sha256": digest.hexdigest()}


def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            chunksize=CHUNK, resumable=True)
    result = api.files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id,name,size",
        supportsAllDrives=True,
    ).execute()
    size = path.stat().st_size
    if int(result.get("size", -1)) != size:
        fail(f"Drive upload size mismatch for {name}")
    return {"name": name, "id": result["id"], "size": size, "sha256": sha256_file(path)}


def build_work_archive(work: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "tar", "-C", str(work),
        "--exclude=./build/nsp",
        "--exclude=./nsp",
        "--exclude=./tools",
        "--exclude=./tmp",
        "--exclude=./aoc/*.img",
        "--exclude=./extract/*/RomFS.img",
        "-cf", "-", ".",
    ]
    tar = subprocess.Popen(command, stdout=subprocess.PIPE)
    assert tar.stdout is not None
    try:
        compressed = subprocess.run(
            ["zstd", "-T0", "-8", "-o", str(destination)],
            stdin=tar.stdout, check=False,
        )
    finally:
        tar.stdout.close()
    if tar.wait() != 0 or compressed.returncode != 0:
        fail("could not create the zstd work archive.")
    if not destination.is_file() or destination.stat().st_size == 0:
        fail("work archive is empty.")


def install_linux_dependencies(root: Path) -> None:
    print("[Link2iOS] Installing Linux build dependencies...")
    subprocess.run(["apt-get", "update", "-qq"], check=True)
    subprocess.run([
        "apt-get", "install", "-y", "-qq", "zstd", "git", "curl",
        "build-essential", "cmake", "ninja-build", "pkg-config", "libssl-dev",
    ], check=True)
    subprocess.run([
        sys.executable, "-m", "pip", "install", "-q", "--upgrade",
        "lz4", "capstone>=5,<6", "fonttools", "zbic", "backports.zstd",
        "google-api-python-client", "google-auth", "requests",
    ], check=True)
    dotnet_root = Path("/content/dotnet")
    dotnet_root.mkdir(exist_ok=True)
    install_script = root / "dotnet-install.sh"
    subprocess.run(["curl", "-fsSL", "https://dot.net/v1/dotnet-install.sh",
                    "-o", str(install_script)], check=True)
    subprocess.run(["bash", str(install_script), "--channel", "10.0",
                    "--install-dir", str(dotnet_root)], check=True)
    os.environ["DOTNET_ROOT"] = str(dotnet_root)
    os.environ["PATH"] = str(dotnet_root) + os.pathsep + os.environ["PATH"]


def prepare(args) -> None:
    # Install the Drive client before the first API call in a fresh Colab runtime.
    subprocess.run([
        sys.executable, "-m", "pip", "install", "-q",
        "google-api-python-client", "google-auth", "requests",
    ], check=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prepare_linux import run_preparation

    api = drive_api()
    request_id = str(uuid.uuid4())
    root = Path("/content/link2ios")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)

    from source_archive import prepare_source
    source = prepare_source(api, args.drive_folder_id, root)
    input_dir = Path(source["nsp_dir"])
    keys_path = Path(source["keys_path"])
    print(f"[Link2iOS] Source ready: {source['nsp_count']} NSP package(s) from {source['source_folder_name']}.")

    install_linux_dependencies(root)
    nx = root / "NX2Apple"
    subprocess.run([
        "git", "clone", "--depth", "1", "--branch", NX2APPLE_TAG,
        "https://github.com/LNPANDY/NX2Apple.git", str(nx),
    ], check=True)
    subprocess.run([sys.executable, str(nx / "tools" / "engine.py"), "sync"],
                   cwd=nx, check=True)
    pin = (nx / ".upstream-ref").read_text(encoding="utf-8").strip()
    if pin != ENGINE_PIN:
        fail(f"NX2Apple release resolved to engine {pin}, expected {ENGINE_PIN}.")

    work = root / "work"
    run_preparation(argparse.Namespace(
        nx2apple_root=nx, nsp_dir=input_dir, keys=keys_path, work_dir=work
    ))
    shutil.rmtree(input_dir, ignore_errors=True)
    keys_path.unlink(missing_ok=True)
    prep = json.loads((work / "link2ios-linux-prep.json").read_text(encoding="utf-8"))
    if prep["title_id"] != TITLE_ID or prep["package_version"] != PACKAGE_VERSION:
        fail("the prepared package is not the supported BOTW 1.9.0 profile.")
    romfs = work / prep["romfs_relative_path"]
    aoc_dir = work / "aoc"
    aoc_dir.mkdir(parents=True, exist_ok=True)
    aoc_files = sorted(aoc_dir.glob("*.img"))
    if not romfs.is_file():
        fail("RomFS image is missing after Linux preparation.")
    if not aoc_files:
        print("[Link2iOS] No DLC was supplied. BOTW base game + update will be built without AOC content.")

    output_id = create_folder(api, f"Link2iOS_BOTW_{request_id[:8]}", args.drive_folder_id)
    pipeline_id = create_folder(api, "pipeline", output_id)
    games_id = create_folder(api, "games", output_id)
    game_id = create_folder(api, TITLE_ID, games_id)
    aoc_id = create_folder(api, "aoc", game_id) if aoc_files else None

    print("[Link2iOS] Uploading external RomFS and any available DLC images...")
    romfs_record = upload_drive_file(api, romfs, game_id, "romfs.img")
    aoc_records = [
        upload_drive_file(api, path, aoc_id, path.name) for path in aoc_files
    ] if aoc_id else []

    archive = root / "botw-work.tar.zst"
    print("[Link2iOS] Archiving build-only workspace; excluding RomFS, AOC, NSPs and Linux tools...")
    build_work_archive(work, archive)
    archive_record = upload_drive_file(api, archive, pipeline_id, "botw-work.tar.zst")

    handoff = {
        "format": 1,
        "project": "Link2iOS",
        "request_id": request_id,
        "branch": BRANCH,
        "title_id": TITLE_ID,
        "package_version": PACKAGE_VERSION,
        "nx2apple_tag": NX2APPLE_TAG,
        "engine_pin": ENGINE_PIN,
        "work_archive": archive_record,
        "game_data": {
            "folder_id": game_id,
            "folder_url": f"https://drive.google.com/drive/folders/{game_id}",
            "romfs": romfs_record,
            "aoc": aoc_records,
            "romfs_relative_path": prep["romfs_relative_path"],
        },
        "prepared": prep,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    handoff_path = Path("/content/link2ios-handoff.json")
    handoff_path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    print("\n[Link2iOS] Linux preparation and Drive uploads completed.")
    print("Extracted source folder:", f"https://drive.google.com/drive/folders/{source['source_folder_id']}")
    print("Game data folder:", handoff["game_data"]["folder_url"])
    print("RomFS:", f"{romfs_record['size']:,} bytes; SHA-256 {romfs_record['sha256']}")
    print("AOC images:", len(aoc_records))
    print("Build workspace:", f"{archive_record['size']:,} bytes; SHA-256 {archive_record['sha256']}")
    print("Handoff file:", handoff_path)
    print("Next: execute the notebook's final cell to commit handoff.json and trigger Link2iOS Actions.")


def dispatch(args) -> None:
    import requests
    handoff_path = args.handoff.resolve()
    if not handoff_path.is_file():
        fail(f"handoff manifest not found: {handoff_path}")
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if handoff.get("branch") != BRANCH or handoff.get("title_id") != TITLE_ID:
        fail("handoff does not belong to Link2iOS / BOTW.")
    token = getpass.getpass(
        "Fine-grained GitHub token (Link2iOS repository, Contents: Read and write): "
    ).strip()
    if not token:
        fail("GitHub token is empty.")

    url = f"https://api.github.com/repos/{REPO}/contents/handoff.json"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    existing = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=30)
    if existing.status_code not in (200, 404):
        fail(f"cannot read branch handoff.json ({existing.status_code}): {existing.text[:1000]}")
    body = {
        "message": f"Queue Link2iOS BOTW build {handoff['request_id'][:8]}",
        "content": base64.b64encode((json.dumps(handoff, indent=2) + "\n").encode()).decode(),
        "branch": BRANCH,
    }
    if existing.status_code == 200:
        body["sha"] = existing.json()["sha"]
    response = requests.put(url, headers=headers, json=body, timeout=60)
    if response.status_code not in (200, 201):
        fail(f"GitHub rejected the handoff commit ({response.status_code}): {response.text[:1500]}")
    print("[Link2iOS] Handoff committed. Only the Link2iOS workflow listens to this file on Link2iOS.")
    print("Commit:", response.json().get("commit", {}).get("html_url", ""))
    print("Actions:", f"https://github.com/{REPO}/actions")
    print("The token was not written to disk or to the handoff.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Link2iOS Colab pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p_prepare = sub.add_parser("prepare", help="download NSPs, run Linux stages and upload outputs to Drive")
    p_prepare.add_argument("--drive-folder-id", required=True)
    p_prepare.set_defaults(func=prepare)
    p_dispatch = sub.add_parser("dispatch", help="commit handoff.json and trigger the Link2iOS workflow")
    p_dispatch.add_argument("--handoff", type=Path, default=Path("/content/link2ios-handoff.json"))
    p_dispatch.set_defaults(func=dispatch)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
