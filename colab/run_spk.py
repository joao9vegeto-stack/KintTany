#!/usr/bin/env python3
"""Drive -> Colab/Linux -> Drive -> GitHub handoff for the isolated SpkIOSzero project."""
from __future__ import annotations
import argparse, base64, datetime as dt, getpass, hashlib, importlib.util, json, os, shutil, subprocess, sys, tarfile, time, uuid
from pathlib import Path, PurePosixPath

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "SpkIOSzero"
PROJECT = "SpkIOSzero"
TITLE_ID = "010035F022078000"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
CHUNK = 64 * 1024 * 1024
FOLDER_MIME = "application/vnd.google-apps.folder"

def fail(message: str) -> None:
    raise SystemExit("[SpkIOSzero] ERROR: " + message)

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
        page = api.files().list(q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000, pageToken=token, orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items.extend(page.get("files", []))
        token = page.get("nextPageToken")
        if not token: return items

def create_folder(api, name: str, parent_id: str) -> str:
    return api.files().create(body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        fields="id,name", supportsAllDrives=True).execute()["id"]

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()

def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    size = path.stat().st_size
    print(f"[SpkIOSzero] Uploading {name}: {size:,} bytes ({size/2**30:.2f} GiB)...", flush=True)
    media = MediaFileUpload(str(path), mimetype="application/octet-stream", chunksize=CHUNK, resumable=True)
    request = api.files().create(body={"name": name, "parents": [parent_id]}, media_body=media,
        fields="id,name,size", supportsAllDrives=True)
    item = None
    while item is None:
        status, item = request.next_chunk()
        if status: print(f"[SpkIOSzero] Drive upload {name}: {status.progress()*100:.1f}%", flush=True)
    if int(item.get("size", -1)) != size: fail(f"Drive upload size mismatch for {name}.")
    record = {"id": item["id"], "name": item["name"], "size": size, "sha256": sha256_file(path)}
    print(f"[SpkIOSzero] Upload verified: {name}; SHA-256 {record['sha256']}", flush=True)
    return record

def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    digest, total = hashlib.sha256(), 0
    with part.open("wb") as stream:
        dl = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
        done, retries = False, 0
        while not done:
            try:
                status, done = dl.next_chunk()
                retries = 0
            except (TimeoutError, ConnectionError, OSError) as exc:
                retries += 1
                if retries > 10: raise RuntimeError(f"Drive download failed after {retries-1} retries: {exc}") from exc
                delay = min(2 ** min(retries, 5), 30)
                print(f"[SpkIOSzero] Drive transfer interrupted at {dl._progress}; retry {retries}/10 in {delay}s.", flush=True)
                time.sleep(delay)
                continue
            if status: print(f"[SpkIOSzero] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
    with part.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block); total += len(block)
    if total != int(item.get("size", -1)):
        part.unlink(missing_ok=True); fail(f"Drive size mismatch for {item.get('name')}: {total} != {item.get('size')}.")
    if digest.hexdigest().lower() != str(item.get("sha256", "")).lower():
        part.unlink(missing_ok=True); fail(f"Drive SHA-256 mismatch for {item.get('name')}.")
    part.replace(destination)

def build_work_archive(work: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "tar", "-C", str(work),
        "--exclude=./tools", "--exclude=./tmp", "--exclude=./aoc/*.img",
        "--exclude=./extract/*/RomFS.img",
        "-cf", "-", ".",
    ]
    tar = subprocess.Popen(command, stdout=subprocess.PIPE)
    assert tar.stdout is not None
    try:
        result = subprocess.run(["zstd", "-T0", "-8", "-o", str(destination)],
            stdin=tar.stdout, check=False)
    finally:
        tar.stdout.close()
    if tar.wait() != 0 or result.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        fail("Could not create the verified zstd build workspace archive.")

def install_nx2apple(root: Path) -> Path:
    nx = root / "NX2Apple"
    pin_file = nx / ".upstream-ref"
    if not nx.is_dir() or not pin_file.is_file() or pin_file.read_text(encoding="utf-8").strip() != ENGINE_PIN:
        shutil.rmtree(nx, ignore_errors=True)
        print(f"[SpkIOSzero] Cloning NX2Apple {NX2APPLE_TAG} and pinning NXNative {ENGINE_PIN}...", flush=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", NX2APPLE_TAG,
                        "https://github.com/LNPANDY/NX2Apple.git", str(nx)], check=True)
        subprocess.run([sys.executable, str(nx / "tools" / "engine.py"), "sync"], cwd=nx, check=True)
    pin = pin_file.read_text(encoding="utf-8").strip()
    if pin != ENGINE_PIN: fail(f"NXNative engine pin mismatch: {pin}.")
    return nx

def prepare(args, api=None) -> dict:
    api = api or drive_api()
    root = Path("/content/spk-ios-zero")
    root.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from source_spk import prepare_source
    source = prepare_source(api, args.drive_folder_id, root, os.environ.get("SPK_BASE_ARCHIVE_URL", "").strip())
    input_dir, keys = Path(source["package_dir"]), Path(source["keys_path"])
    print(f"[SpkIOSzero] Source ready: {source['package_count']} NSPs from Drive/{source['source_folder_name']}; BOTW inputs were not read.", flush=True)

    from prepare_spk import run_preparation
    nx = install_nx2apple(root)
    work = root / "work"
    if work.exists():
        # Keep source files and keys, but start a new game-build workspace to avoid stale manifests.
        shutil.rmtree(work)
    work.mkdir(parents=True)
    prep = run_preparation(argparse.Namespace(nx2apple_root=nx, nsp_dir=input_dir, keys=keys, work_dir=work))
    if prep.get("project") != PROJECT or prep.get("title_id") != TITLE_ID:
        fail("Colab preparation manifest does not belong to Sparking! ZERO.")
    if prep.get("nx2apple_tag") != NX2APPLE_TAG or prep.get("engine_pin") != ENGINE_PIN:
        fail("Colab preparation was made with another NX2Apple/NXNative pin.")
    romfs = work / prep["romfs_relative_path"]
    romfs_id = work / prep["romfs_id_relative_path"]
    aoc_dir = work / prep["aoc_relative_dir"]
    aoc_files = sorted(p for p in aoc_dir.glob("*.img") if p.is_file())
    expected_aoc = {x["name"] for x in prep.get("aoc_images", [])}
    if not romfs.is_file() or romfs.stat().st_size != int(prep["romfs_size"]): fail("Prepared external RomFS is missing or has the wrong size.")
    if not romfs_id.is_file(): fail("RomFS identity sidecar is missing from the NX2Apple-patched extraction.")
    if not aoc_files or {p.name for p in aoc_files} != expected_aoc:
        fail(f"DLC AOC image set differs from the preparation manifest: {sorted(p.name for p in aoc_files)} != {sorted(expected_aoc)}.")

    request_id = str(uuid.uuid4())
    output_id = create_folder(api, f"SpkIOSzero_{request_id[:8]}", args.drive_folder_id)
    pipeline_id = create_folder(api, "pipeline", output_id)
    games_id = create_folder(api, "games", output_id)
    game_id = create_folder(api, TITLE_ID, games_id)
    aoc_id = create_folder(api, "aoc", game_id)
    print("[SpkIOSzero] Uploading the game RomFS and each DLC AOC image as external Drive data...", flush=True)
    romfs_record = upload_drive_file(api, romfs, game_id, "romfs.img")
    aoc_records = [upload_drive_file(api, image, aoc_id, image.name) for image in aoc_files]

    archive = root / "spk-work.tar.zst"
    print("[SpkIOSzero] Archiving build workspace only; excluding the base/update/DLC NSPs, prod.keys, RomFS, AOC images, tools and tmp.", flush=True)
    build_work_archive(work, archive)
    archive_record = upload_drive_file(api, archive, pipeline_id, "spk-work.tar.zst")
    handoff = {
        "format": 1, "project": PROJECT, "branch": BRANCH, "request_id": request_id,
        "title_id": TITLE_ID, "package_version": prep["package_version"],
        "nx2apple_tag": NX2APPLE_TAG, "engine_pin": ENGINE_PIN,
        "drive_output_folder_id": output_id,
        "drive_output_folder_url": f"https://drive.google.com/drive/folders/{output_id}",
        "work_archive": archive_record,
        "game_data": {
            "folder_id": game_id, "folder_url": f"https://drive.google.com/drive/folders/{game_id}",
            "romfs": romfs_record, "aoc": aoc_records,
            "romfs_relative_path": prep["romfs_relative_path"],
            "aoc_relative_dir": prep["aoc_relative_dir"],
        },
        "prepared": prep,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    handoff_path = Path("/content/spk-ios-zero-handoff.json")
    handoff_path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    manifest_record = upload_drive_file(api, handoff_path, output_id, "handoff.json")
    print("\n[SpkIOSzero] Colab/Linux preparation and Drive checkpoints completed.", flush=True)
    print("Request:", request_id)
    print("Drive:", handoff["drive_output_folder_url"])
    print("RomFS:", f"{romfs_record['size']:,} bytes; SHA-256 {romfs_record['sha256']}")
    print("DLC AOC:", ", ".join(x["name"] for x in aoc_records))
    print("Workspace:", f"{archive_record['size']:,} bytes; SHA-256 {archive_record['sha256']}")
    print("Handoff manifest Drive ID:", manifest_record["id"])
    print("Next: execute dispatch to commit handoff.json on SpkIOSzero and trigger only the SpkIOSzero workflow.")
    return handoff

def recover(args, api=None) -> dict | None:
    from googleapiclient.http import MediaIoBaseDownload
    api = api or drive_api()
    folders = [x for x in list_children(api, args.drive_folder_id)
        if x.get("mimeType") == FOLDER_MIME and x.get("name", "").startswith("SpkIOSzero_")]
    folders.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)
    for folder in folders:
        manifest = next((x for x in list_children(api, folder["id"])
            if x.get("mimeType") != FOLDER_MIME and x.get("name", "").lower() == "handoff.json"), None)
        if not manifest: continue
        dest = Path("/content/spk-ios-zero-handoff.json")
        temp = dest.with_suffix(".json.part")
        request = api.files().get_media(fileId=manifest["id"], supportsAllDrives=True)
        with temp.open("wb") as stream:
            dl = MediaIoBaseDownload(stream, request, chunksize=1024*1024)
            done = False
            while not done: _, done = dl.next_chunk()
        temp.replace(dest)
        handoff = json.loads(dest.read_text(encoding="utf-8"))
        prepared = handoff.get("prepared") or {}
        if (handoff.get("project") != PROJECT or handoff.get("branch") != BRANCH
            or handoff.get("title_id") != TITLE_ID or handoff.get("nx2apple_tag") != NX2APPLE_TAG
            or handoff.get("engine_pin") != ENGINE_PIN or not handoff.get("work_archive", {}).get("id")
            or not handoff.get("game_data", {}).get("romfs", {}).get("id")
            or handoff.get("package_version") != prepared.get("package_version")
            or not prepared.get("aoc_images") or not handoff.get("game_data", {}).get("aoc")):
            dest.unlink(missing_ok=True)
            continue
        print("[SpkIOSzero] Completed Sparking! ZERO handoff recovered from Drive; no NSP download, extraction or rewrite was repeated.")
        print("Request:", handoff["request_id"])
        print("Drive:", handoff.get("drive_output_folder_url"))
        print("Package:", handoff["package_version"])
        print("AOC images:", ", ".join(x["name"] for x in handoff["game_data"]["aoc"]))
        print("Local manifest:", dest)
        return handoff
    print("[SpkIOSzero] No completed SpkIOSzero preparation was found in the configured Drive folder.")
    return None

def dispatch(args) -> None:
    import requests
    handoff_path = args.handoff.resolve()
    if not handoff_path.is_file(): fail(f"Handoff manifest not found: {handoff_path}")
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if (handoff.get("project") != PROJECT or handoff.get("branch") != BRANCH
        or handoff.get("title_id") != TITLE_ID or handoff.get("nx2apple_tag") != NX2APPLE_TAG
        or handoff.get("engine_pin") != ENGINE_PIN):
        fail("Handoff does not belong to this SpkIOSzero branch/game/engine pin.")
    token = getpass.getpass("Fine-grained GitHub token (KintTany repository, Contents: Read and write): ").strip()
    if not token: fail("GitHub token is empty.")
    url = f"https://api.github.com/repos/{REPO}/contents/handoff.json"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    existing = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=30)
    if existing.status_code not in (200, 404):
        fail(f"Cannot read {BRANCH}/handoff.json ({existing.status_code}): {existing.text[:1000]}")
    body = {"message": f"Queue SpkIOSzero build {handoff['request_id'][:8]}",
            "content": base64.b64encode((json.dumps(handoff, indent=2) + "\n").encode()).decode(),
            "branch": BRANCH}
    if existing.status_code == 200: body["sha"] = existing.json()["sha"]
    response = requests.put(url, headers=headers, json=body, timeout=60)
    if response.status_code not in (200, 201):
        fail(f"GitHub rejected the SpkIOSzero handoff commit ({response.status_code}): {response.text[:1500]}")
    print("[SpkIOSzero] Handoff committed to SpkIOSzero. No other branch was targeted.")
    print("Commit:", response.json().get("commit", {}).get("html_url", ""))
    print("Actions:", f"https://github.com/{REPO}/actions")
    print("The token was used in memory only; it was not written to Drive or the repository.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Sparking! ZERO isolated Colab pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="download only Drive/spk NSPs, prepare on Linux, upload build data")
    p.add_argument("--drive-folder-id", required=True); p.set_defaults(func=prepare)
    p = sub.add_parser("recover", help="recover the latest completed SPK handoff without rebuilding")
    p.add_argument("--drive-folder-id", required=True); p.set_defaults(func=recover)
    p = sub.add_parser("dispatch", help="commit handoff.json on SpkIOSzero and trigger Actions")
    p.add_argument("--handoff", type=Path, default=Path("/content/spk-ios-zero-handoff.json")); p.set_defaults(func=dispatch)
    args = parser.parse_args(); args.func(args)

if __name__ == "__main__": main()
