#!/usr/bin/env python3
"""Google Drive -> Colab/Linux -> Drive -> Link2iOS GitHub handoff."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import getpass
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
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


def drive_api(credentials=None):
    """Build a Drive client using the Colab user's OAuth credentials (no Colab Secret)."""
    from googleapiclient.discovery import build
    if credentials is None:
        try:
            import google.auth
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/drive"]
            )
        except Exception as exc:
            fail(
                "Google Drive não autenticado. Execute auth.authenticate_user() "
                "no notebook antes da preparação. "
                f"Detalhe: {type(exc).__name__}: {exc}"
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
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)",
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
    expected = int(item.get("size") or 0)
    if destination.is_file() and expected and destination.stat().st_size == expected:
        print(f"[Link2iOS] Reusing {item.get('name', item['id'])}: {expected:,} bytes already present.")
        return
    temp = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    digest, total = hashlib.sha256(), 0
    started = time.monotonic()
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
    elapsed = max(time.monotonic() - started, 0.001)
    print(
        f"[Link2iOS] Download verified: {item.get('name', item['id'])} — "
        f"{total:,} bytes ({total / 1024**3:.2f} GiB) in {elapsed:.1f}s "
        f"({total / elapsed / 1024**2:.1f} MiB/s).",
        flush=True,
    )
    return {"name": item["name"], "id": item["id"], "size": total, "sha256": digest.hexdigest()}


def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    started = time.monotonic()
    size = path.stat().st_size
    print(f"[Link2iOS] Enviando {name}: {size:,} bytes ({size / 1024**3:.2f} GiB)...", flush=True)
    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            chunksize=CHUNK, resumable=True)
    request = api.files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id,name,size",
        supportsAllDrives=True,
    )
    result = None
    while result is None:
        status, result = request.next_chunk()
        if status:
            print(
                f"[Link2iOS] Upload {name}: {status.progress() * 100:.1f}%",
                flush=True,
            )
    size = path.stat().st_size
    if int(result.get("size", -1)) != size:
        fail(f"Drive upload size mismatch for {name}")
    elapsed = max(time.monotonic() - started, 0.001)
    print(
        f"[Link2iOS] Upload verificado: {name} — {size:,} bytes em {elapsed:.1f}s "
        f"({size / elapsed / 1024**2:.1f} MiB/s).",
        flush=True,
    )
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
    print("[Link2iOS] Verificando dependências locais do Colab...")

    apt_commands = ("zstd", "git", "curl", "cmake", "ninja", "pkg-config")
    missing_commands = [name for name in apt_commands if shutil.which(name) is None]

    def apt_package_installed(name: str) -> bool:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${db:Status-Status}", name],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "installed"

    apt_packages = ("build-essential", "libssl-dev")
    missing_packages = [name for name in apt_packages if not apt_package_installed(name)]
    missing_apt = list(dict.fromkeys([*missing_commands, *missing_packages]))
    if missing_apt:
        print("[Link2iOS] Instalando pacotes ausentes:", ", ".join(missing_apt))
        subprocess.run(["apt-get", "update", "-qq"], check=True)
        subprocess.run([
            "apt-get", "install", "-y", "-qq", *missing_apt,
        ], check=True)
    else:
        print("[Link2iOS] Dependências APT já instaladas; pulando apt-get update/install.")

    python_modules = (
        ("lz4.block", "lz4"),
        ("capstone", "capstone>=5,<6"),
        ("fontTools", "fonttools"),
        ("zbic", "zbic"),
        ("backports.zstd", "backports.zstd"),
        ("googleapiclient.discovery", "google-api-python-client"),
        ("google.auth", "google-auth"),
        ("requests", "requests"),
    )
    missing_pip = []
    for module_name, package_name in python_modules:
        try:
            if importlib.util.find_spec(module_name) is None:
                missing_pip.append(package_name)
        except (ImportError, ModuleNotFoundError, ValueError):
            missing_pip.append(package_name)
    if missing_pip:
        packages = list(dict.fromkeys(missing_pip))
        print("[Link2iOS] Instalando módulos Python ausentes:", ", ".join(packages))
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-q", *packages,
        ], check=True)
    else:
        print("[Link2iOS] Módulos Python já instalados; pulando pip install.")

    dotnet_root = Path("/content/dotnet").resolve()
    dotnet = dotnet_root / "dotnet"
    runtime_env = os.environ.copy()
    if dotnet.is_file():
        runtime_env.update({
            "DOTNET_ROOT": str(dotnet_root),
            "DOTNET_ROOT_X64": str(dotnet_root),
            "DOTNET_HOST_PATH": str(dotnet),
            "PATH": str(dotnet_root) + os.pathsep + runtime_env.get("PATH", ""),
        })
        runtime_check = subprocess.run(
            [str(dotnet), "--list-runtimes"], env=runtime_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        runtimes = runtime_check.stdout if runtime_check.returncode == 0 else ""
    else:
        runtimes = ""

    if not re.search(r"^Microsoft\\.NETCore\\.App\\s+10\\.", runtimes, re.MULTILINE):
        dotnet_root.mkdir(parents=True, exist_ok=True)
        install_script = root / "dotnet-install.sh"
        subprocess.run(["curl", "-fsSL", "https://dot.net/v1/dotnet-install.sh",
                        "-o", str(install_script)], check=True)
        subprocess.run(["bash", str(install_script), "--channel", "10.0",
                        "--install-dir", str(dotnet_root)], check=True)
        runtime_env = os.environ.copy()
        runtime_env.update({
            "DOTNET_ROOT": str(dotnet_root),
            "DOTNET_ROOT_X64": str(dotnet_root),
            "DOTNET_HOST_PATH": str(dotnet),
            "PATH": str(dotnet_root) + os.pathsep + runtime_env.get("PATH", ""),
        })
        runtimes = subprocess.run(
            [str(dotnet), "--list-runtimes"], env=runtime_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True,
        ).stdout
    else:
        print("[Link2iOS] .NET 10 já instalado; pulando download/instalação.")

    if not dotnet.is_file():
        fail(f".NET 10 não encontrado após a instalação: {dotnet}")
    if not re.search(r"^Microsoft\\.NETCore\\.App\\s+10\\.", runtimes, re.MULTILINE):
        fail(
            ".NET SDK foi instalado, mas o runtime Microsoft.NETCore.App 10.x "
            f"não aparece em dotnet --list-runtimes. Saída: {runtimes[-2000:]}"
        )
    os.environ.update({
        "DOTNET_ROOT": str(dotnet_root),
        "DOTNET_ROOT_X64": str(dotnet_root),
        "DOTNET_HOST_PATH": str(dotnet),
        "PATH": str(dotnet_root) + os.pathsep + os.environ.get("PATH", ""),
    })
    print("[Link2iOS] .NET 10 validado para apphost x64:")
    print(runtimes.strip())


def prepare(args, api=None) -> None:
    # Install the Drive client before the first API call in a fresh Colab runtime.
    subprocess.run([
        sys.executable, "-m", "pip", "install", "-q",
        "google-api-python-client", "google-auth", "requests",
    ], check=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prepare_linux import run_preparation

    api = api or drive_api()
    request_id = str(uuid.uuid4())
    root = Path("/content/link2ios")
    root.mkdir(parents=True, exist_ok=True)
    print("[Link2iOS] Runtime workspace preserved. Existing partial work/downloads will be reused where their fingerprints match.")

    from source_archive import prepare_source
    source = prepare_source(api, args.drive_folder_id, root)
    input_dir = Path(source["package_dir"])
    keys_path = Path(source["keys_path"])
    print(
        f"[Link2iOS] Source ready: {source['package_count']} Switch packages "
        f"(1 {source['base_type']} base + {source['update_nsp_count']} update + "
        f"{source['dlc_nsp_count']} DLC) from {source['source_folder_name']}."
    )

    install_linux_dependencies(root)
    nx = root / "NX2Apple"
    pinned_file = nx / ".upstream-ref"
    if not nx.is_dir() or not pinned_file.is_file() or pinned_file.read_text(encoding="utf-8").strip() != ENGINE_PIN:
        shutil.rmtree(nx, ignore_errors=True)
        print(f"[Link2iOS] Clonando NX2Apple {NX2APPLE_TAG} e fixando NXNative {ENGINE_PIN}...")
        subprocess.run([
            "git", "clone", "--depth", "1", "--branch", NX2APPLE_TAG,
            "https://github.com/LNPANDY/NX2Apple.git", str(nx),
        ], check=True)
        subprocess.run([sys.executable, str(nx / "tools" / "engine.py"), "sync"],
                       cwd=nx, check=True)
    else:
        print(f"[Link2iOS] Reutilizando NX2Apple/NXNative já fixado em {ENGINE_PIN}.")
    pin = (nx / ".upstream-ref").read_text(encoding="utf-8").strip()
    if pin != ENGINE_PIN:
        fail(f"NX2Apple release resolved to engine {pin}, expected {ENGINE_PIN}.")

    work = root / "work"
    run_preparation(argparse.Namespace(
        nx2apple_root=nx, nsp_dir=input_dir, keys=keys_path, work_dir=work
    ))
    # Keep downloaded packages and keys until the Drive checkpoint is fully uploaded.
    # If a later upload fails, the next cell retry can reuse the same local inputs.
    prep = json.loads((work / "link2ios-linux-prep.json").read_text(encoding="utf-8"))
    if prep["title_id"] != TITLE_ID or prep["package_version"] != PACKAGE_VERSION:
        fail("the prepared package is not the supported BOTW 1.9.0 profile.")
    romfs = work / prep["romfs_relative_path"]
    aoc_dir = work / "aoc"
    aoc_dir.mkdir(parents=True, exist_ok=True)
    aoc_files = sorted(aoc_dir.glob("*.img"))
    expected_aoc = {"1.img", "2.img"}
    actual_aoc = {path.name for path in aoc_files}
    if not romfs.is_file() or not romfs.stat().st_size:
        fail("RomFS image is missing or empty after Linux preparation.")
    if actual_aoc != expected_aoc or any(path.stat().st_size <= 0 for path in aoc_files):
        fail(
            "BOTW requires both DLC outputs: aoc/1.img (01007EF00011F001) and "
            f"aoc/2.img (01007EF00011F002); NX2Native produced {sorted(actual_aoc)}."
        )
    if prep.get("aoc_title_ids") != {
        "1.img": "01007EF00011F001",
        "2.img": "01007EF00011F002",
    }:
        fail("Colab preparation manifest does not identify both BOTW DLC content IDs.")

    output_id = create_folder(api, f"Link2iOS_BOTW_{request_id[:8]}", args.drive_folder_id)
    pipeline_id = create_folder(api, "pipeline", output_id)
    games_id = create_folder(api, "games", output_id)
    game_id = create_folder(api, TITLE_ID, games_id)
    aoc_id = create_folder(api, "aoc", game_id) if aoc_files else None

    print("[Link2iOS] Uploading external RomFS and required DLC AOC images...")
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
        "drive_output_folder_id": output_id,
        "drive_output_folder_url": f"https://drive.google.com/drive/folders/{output_id}",
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
    handoff_manifest = upload_drive_file(api, handoff_path, output_id, "handoff.json")
    # Keep the source packages, keys, NX2Apple checkout and build workspace on
    # Colab's local disk. Retrying a failed stage must not re-download multi-GB inputs.
    package_cache_bytes = sum(p.stat().st_size for p in input_dir.iterdir() if p.is_file())
    print(f"[Link2iOS] Cache de origem preservado em {input_dir} ({package_cache_bytes:,} bytes + prod.keys).")
    print("\n[Link2iOS] Linux preparation and Drive uploads completed.")
    print("Recovery manifest uploaded:", handoff_manifest["id"])
    print("Extracted source folder:", f"https://drive.google.com/drive/folders/{source['source_folder_id']}")
    print("Game data folder:", handoff["game_data"]["folder_url"])
    print("RomFS:", f"{romfs_record['size']:,} bytes; SHA-256 {romfs_record['sha256']}")
    print("AOC images:", len(aoc_records))
    print("Build workspace:", f"{archive_record['size']:,} bytes; SHA-256 {archive_record['sha256']}")
    print("Handoff file:", handoff_path)
    print("Next: execute the notebook's final cell to commit handoff.json and trigger Link2iOS Actions.")


def recover(args, api=None) -> dict | None:
    """Restore a completed BOTW handoff manifest from Drive without downloading/rebuilding game data."""
    from googleapiclient.http import MediaIoBaseDownload

    api = api or drive_api()
    root_items = list_children(api, args.drive_folder_id)
    run_folders = [
        item for item in root_items
        if item.get("mimeType") == "application/vnd.google-apps.folder"
        and item.get("name", "").startswith("Link2iOS_BOTW_")
    ]
    run_folders.sort(key=lambda item: item.get("modifiedTime", ""), reverse=True)

    for folder in run_folders:
        manifest = next((
            item for item in list_children(api, folder["id"])
            if item.get("mimeType") != "application/vnd.google-apps.folder"
            and item.get("name", "").lower() == "handoff.json"
        ), None)
        if manifest is None:
            continue
        destination = Path("/content/link2ios-handoff.json")
        temp = destination.with_suffix(".json.part")
        request = api.files().get_media(fileId=manifest["id"], supportsAllDrives=True)
        with temp.open("wb") as output:
            downloader = MediaIoBaseDownload(output, request, chunksize=1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        temp.replace(destination)
        handoff = json.loads(destination.read_text(encoding="utf-8"))
        if handoff.get("project") != "Link2iOS" or handoff.get("branch") != BRANCH:
            destination.unlink(missing_ok=True)
            continue
        if handoff.get("title_id") != TITLE_ID or handoff.get("package_version") != PACKAGE_VERSION:
            destination.unlink(missing_ok=True)
            continue
        aoc = handoff.get("game_data", {}).get("aoc", [])
        prep_aoc = handoff.get("prepared", {}).get("aoc_images", [])
        expected_aoc = {"1.img", "2.img"}
        aoc_names = {Path(item.get("name", "")).name for item in aoc}
        prep_names = {Path(item.get("name", "")).name for item in prep_aoc}
        if not handoff.get("work_archive", {}).get("id"):
            destination.unlink(missing_ok=True)
            continue
        if not handoff.get("game_data", {}).get("romfs", {}).get("id"):
            destination.unlink(missing_ok=True)
            continue
        if (
            aoc_names != expected_aoc
            or prep_names != expected_aoc
            or len(aoc) != 2
            or len(prep_aoc) != 2
            or handoff.get("prepared", {}).get("aoc_title_ids") != {
                "1.img": "01007EF00011F001",
                "2.img": "01007EF00011F002",
            }
        ):
            destination.unlink(missing_ok=True)
            continue
        print("[Link2iOS] PREPARAÇÃO BOTW EXISTENTE RECUPERADA.")
        print("Request:", handoff.get("request_id"))
        print("Drive run:", handoff.get("drive_output_folder_url", folder.get("webViewLink", folder["id"])))
        print("Workspace archive:", handoff["work_archive"].get("size"), "bytes")
        print("RomFS:", handoff["game_data"]["romfs"].get("size"), "bytes")
        print("AOC images:", ", ".join(sorted(aoc_names)))
        print("Nenhum XCI/NSP foi baixado; nenhuma extração, rewrite ou shader split foi executado.")
        print("Handoff local:", destination)
        return handoff

    print("[Link2iOS] Nenhuma preparação BOTW 1.9.0 completa foi encontrada no Drive.")
    print("[Link2iOS] A recuperação ignorou as pastas e arquivos de Kleo2iOS/ outros projetos.")
    return None


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
    p_prepare = sub.add_parser("prepare", help="download XCI/NSP packages, run Linux stages and upload outputs to Drive")
    p_prepare.add_argument("--drive-folder-id", required=True)
    p_prepare.set_defaults(func=prepare)
    p_recover = sub.add_parser("recover", help="restore the latest completed BOTW handoff from Drive without rebuilding")
    p_recover.add_argument("--drive-folder-id", required=True)
    p_recover.set_defaults(func=recover)
    p_dispatch = sub.add_parser("dispatch", help="commit handoff.json and trigger the Link2iOS workflow")
    p_dispatch.add_argument("--handoff", type=Path, default=Path("/content/link2ios-handoff.json"))
    p_dispatch.set_defaults(func=dispatch)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
