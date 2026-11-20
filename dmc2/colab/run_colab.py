#!/usr/bin/env python3
"""Google Drive -> Colab/Linux -> Drive -> Dante2iOS GitHub handoff."""
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
BRANCH = "Dante2iOS"
TITLE_ID = "01007CF00D5BA000"
PACKAGE_VERSION = "v0"
NX2APPLE_REF = "Dante2iOS"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"
CHUNK = 64 * 1024 * 1024


def fail(message: str) -> None:
    raise SystemExit("[Dante2iOS] ERROR: " + message)


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
        print(f"[Dante2iOS] Reusing {item.get('name', item['id'])}: {expected:,} bytes already present.")
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
        f"[Dante2iOS] Download verified: {item.get('name', item['id'])} — "
        f"{total:,} bytes ({total / 1024**3:.2f} GiB) in {elapsed:.1f}s "
        f"({total / elapsed / 1024**2:.1f} MiB/s).",
        flush=True,
    )
    return {"name": item["name"], "id": item["id"], "size": total, "sha256": digest.hexdigest()}


def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    started = time.monotonic()
    size = path.stat().st_size
    print(f"[Dante2iOS] Enviando {name}: {size:,} bytes ({size / 1024**3:.2f} GiB)...", flush=True)
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
                f"[Dante2iOS] Upload {name}: {status.progress() * 100:.1f}%",
                flush=True,
            )
    size = path.stat().st_size
    if int(result.get("size", -1)) != size:
        fail(f"Drive upload size mismatch for {name}")
    elapsed = max(time.monotonic() - started, 0.001)
    print(
        f"[Dante2iOS] Upload verificado: {name} — {size:,} bytes em {elapsed:.1f}s "
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
    print("[Dante2iOS] Verificando dependências locais do Colab...")

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
        print("[Dante2iOS] Instalando pacotes ausentes:", ", ".join(missing_apt))
        subprocess.run(["apt-get", "update", "-qq"], check=True)
        subprocess.run([
            "apt-get", "install", "-y", "-qq", *missing_apt,
        ], check=True)
    else:
        print("[Dante2iOS] Dependências APT já instaladas; pulando apt-get update/install.")

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
        print("[Dante2iOS] Instalando módulos Python ausentes:", ", ".join(packages))
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-q", *packages,
        ], check=True)
    else:
        print("[Dante2iOS] Módulos Python já instalados; pulando pip install.")

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

    if not re.search(r"^Microsoft\.NETCore\.App\s+10\.", runtimes, re.MULTILINE):
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
        print("[Dante2iOS] .NET 10 já instalado; pulando download/instalação.")

    if not dotnet.is_file():
        fail(f".NET 10 não encontrado após a instalação: {dotnet}")
    if not re.search(r"^Microsoft\.NETCore\.App\s+10\.", runtimes, re.MULTILINE):
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
    print("[Dante2iOS] .NET 10 validado para apphost x64:")
    print(runtimes.strip())



def prepare(args, api=None) -> dict:
    for module_name, name in (("googleapiclient.discovery", "google-api-python-client"),
                              ("google.auth", "google-auth"), ("requests", "requests")):
        try:
            found = importlib.util.find_spec(module_name)
        except (ImportError, ValueError, ModuleNotFoundError):
            found = None
        if found is None:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", name], check=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prepare_linux import run_preparation
    from source_archive import prepare_source
    api = api or drive_api()
    root = Path("/content/dante2ios")
    root.mkdir(parents=True, exist_ok=True)
    source = prepare_source(api, args.drive_folder_id, root)
    if source["package_count"] != 1 or source["update_nsp_count"] or source["dlc_nsp_count"]:
        fail("DMC2 must have exactly one base NSP and no update or DLC")
    install_linux_dependencies(root)
    nx = root / "NX2Apple"
    if (nx / ".upstream-ref").is_file() and (nx / ".upstream-ref").read_text().strip() != ENGINE_PIN:
        shutil.rmtree(nx)
    if not (nx / ".upstream-ref").is_file():
        shutil.rmtree(nx, ignore_errors=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH,
                        f"https://github.com/{REPO}.git", str(nx)], check=True)
        subprocess.run([sys.executable, str(nx / "tools/engine.py"), "check"], cwd=nx, check=True)
        subprocess.run([sys.executable, str(nx / "tools/engine.py"), "sync"], cwd=nx, check=True)
        subprocess.run([sys.executable, str(nx / "tools/engine.py"), "relink"], cwd=nx, check=True)
    if (nx / ".upstream-ref").read_text().strip() != ENGINE_PIN:
        fail("Dante2iOS upstream pin differs from the validated DMC2 build pin")
    work = root / "work"
    prep = run_preparation(argparse.Namespace(nx2apple_root=nx, nsp_dir=Path(source["package_dir"]),
        keys=Path(source["keys_path"]), work_dir=work))
    if prep["title_id"] != TITLE_ID or prep["package_version"] != PACKAGE_VERSION:
        fail("NXNative extracted a different game or package version")
    romfs = work / prep["romfs_relative_path"]
    if not romfs.is_file() or romfs.stat().st_size == 0:
        fail("RomFS missing or empty")
    if (work / "aoc").is_dir() and list((work / "aoc").glob("*.img")):
        fail("Unexpected AOC in DMC2 base-only build")
    request_id = str(uuid.uuid4())
    output_id = create_folder(api, f"Dante2iOS_DMC2_{request_id[:8]}", source["game_folder_id"])
    pipeline_id = create_folder(api, "pipeline", output_id)
    game_id = create_folder(api, TITLE_ID, create_folder(api, "games", output_id))
    print("[Dante2iOS] Enviando RomFS externa (a IPA não a incorporará).")
    romfs_record = upload_drive_file(api, romfs, game_id, "romfs.img")
    archive = root / "dmc2-work.tar.zst"
    build_work_archive(work, archive)
    archive_record = upload_drive_file(api, archive, pipeline_id, archive.name)
    handoff = {
        "format": 1, "project": "Dante2iOS", "branch": BRANCH,
        "request_id": request_id, "title_id": TITLE_ID,
        "package_version": PACKAGE_VERSION, "source_ref": NX2APPLE_REF,
        "engine_pin": ENGINE_PIN,
        "source_commit": subprocess.check_output(["git", "-C", str(nx), "rev-parse", "HEAD"], text=True).strip(),
        "drive_output_folder_id": output_id,
        "drive_output_folder_url": f"https://drive.google.com/drive/folders/{output_id}",
        "work_archive": archive_record, "game_data": {
            "folder_id": game_id,
            "folder_url": f"https://drive.google.com/drive/folders/{game_id}",
            "romfs": romfs_record, "aoc": [],
            "romfs_relative_path": prep["romfs_relative_path"],
        },
        "prepared": prep, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    path = Path("/content/dante2ios-handoff.json")
    path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    upload_drive_file(api, path, output_id, "handoff.json")
    print("[Dante2iOS] PREPARAÇÃO E UPLOAD VERIFICADOS.")
    print("Title ID:", TITLE_ID, "| graphics:", prep["graphics"], "| provisional:", prep["provisional"])
    print("RomFS:", romfs_record["size"], "bytes")
    print("Prepared archive:", archive_record["size"], "bytes")
    print("Recovery folder:", handoff["drive_output_folder_url"])
    print("Execute a célula final para publicar apenas dmc2/handoff.json e disparar o Actions.")
    return handoff


def recover(args, api=None) -> dict | None:
    from googleapiclient.http import MediaIoBaseDownload
    api = api or drive_api()
    game_folders = [x for x in list_children(api, args.drive_folder_id)
                    if x["name"].casefold() == "dmc2"
                    and x.get("mimeType") == "application/vnd.google-apps.folder"]
    if len(game_folders) != 1:
        fail("A pasta dmc2 não foi encontrada na pasta compartilhada.")
    run_folders = [x for x in list_children(api, game_folders[0]["id"])
                   if x.get("mimeType") == "application/vnd.google-apps.folder"
                   and x["name"].startswith("Dante2iOS_DMC2_")]
    run_folders.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)
    for folder in run_folders:
        items = [x for x in list_children(api, folder["id"]) if x["name"] == "handoff.json"]
        if len(items) != 1:
            continue
        path = Path("/content/dante2ios-handoff.json")
        tmp = path.with_suffix(".part")
        req = api.files().get_media(fileId=items[0]["id"], supportsAllDrives=True)
        with tmp.open("wb") as out:
            dl = MediaIoBaseDownload(out, req, chunksize=1024*1024)
            done = False
            while not done:
                _, done = dl.next_chunk()
        tmp.replace(path)
        try:
            d = json.loads(path.read_text())
        except (ValueError, OSError):
            path.unlink(missing_ok=True)
            continue
        p = d.get("prepared", {})
        if not (d.get("project") == "Dante2iOS" and d.get("branch") == BRANCH
                and d.get("title_id") == TITLE_ID and d.get("package_version") == PACKAGE_VERSION
                and d.get("engine_pin") == ENGINE_PIN
                and d.get("work_archive", {}).get("id")
                and d.get("game_data", {}).get("romfs", {}).get("id")
                and d.get("game_data", {}).get("aoc") == []
                and p.get("graphics") in ("nvn", "gl", "vulkan")):
            path.unlink(missing_ok=True)
            continue
        print("[Dante2iOS] Recuperado sem baixar NSP nem refazer a preparação:", d["request_id"])
        return d
    print("[Dante2iOS] Nenhuma preparação verificada foi encontrada. Execute a primeira preparação.")
    return None


def dispatch(args) -> None:
    import requests
    path = args.handoff.resolve()
    if not path.is_file():
        fail(f"Handoff ausente: {path}")
    d = json.loads(path.read_text())
    if d.get("project") != "Dante2iOS" or d.get("branch") != BRANCH or d.get("title_id") != TITLE_ID:
        fail("Handoff pertence a outro projeto ou jogo")
    token = getpass.getpass("Fine-grained GitHub PAT (Contents: Read and write; acesso apenas a KintTany): ").strip()
    if not token:
        fail("GitHub token vazio")
    url = f"https://api.github.com/repos/{REPO}/contents/dmc2/handoff.json"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    old = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=30)
    if old.status_code not in (200, 404):
        fail(f"GitHub GET falhou: {old.status_code} {old.text[:300]}")
    if old.status_code == 200:
        import base64 as _b64
        prior = json.loads(_b64.b64decode(old.json()["content"]).decode())
        if prior.get("request_id") == d["request_id"]:
            fail("Este request_id já foi enviado. Não crie outro commit/workflow para o mesmo handoff.")
    body = {"message": f"Dante2iOS DMC2: build request {d['request_id'][:8]}",
            "content": base64.b64encode((json.dumps(d, indent=2) + "\n").encode()).decode(),
            "branch": BRANCH}
    if old.status_code == 200:
        body["sha"] = old.json()["sha"]
    response = requests.put(url, headers=headers, json=body, timeout=60)
    if response.status_code not in (200, 201):
        fail(f"GitHub PUT falhou: {response.status_code} {response.text[:300]}")
    print("[Dante2iOS] Um commit de handoff; um workflow (DMC2) será disparado.")
    print("Commit:", response.json().get("commit", {}).get("html_url"))
    print("Actions:", f"https://github.com/{REPO}/actions")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dante2iOS DMC2 - Colab to Drive to Actions")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("prepare", prepare), ("recover", recover)):
        p = sub.add_parser(name)
        p.add_argument("--drive-folder-id", required=True)
        p.set_defaults(func=handler)
    p = sub.add_parser("dispatch")
    p.add_argument("--handoff", type=Path, default=Path("/content/dante2ios-handoff.json"))
    p.set_defaults(func=dispatch)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
