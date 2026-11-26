#!/usr/bin/env python3
"""Google Drive -> Colab/Linux -> Drive -> Nier2iOS GitHub handoff."""
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
BRANCH = "Nier2iOS"
TITLE_ID = "010056B015FE8000"
NX2APPLE_REF = "Nier2iOS"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"
CHUNK = 64 * 1024 * 1024


def fail(message: str) -> None:
    raise SystemExit("[Nier2iOS] ERROR: " + message)


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


# Use the identical chunked downloader for Colab recovery and source transfers.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drive_chunks import download_drive_file as _download_chunks


def download_drive_file(api, item: dict, destination: Path) -> dict:
    return _download_chunks(api, item, destination)


def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    started = time.monotonic()
    size = path.stat().st_size
    print(f"[Nier2iOS] Enviando {name}: {size:,} bytes ({size / 1024**3:.2f} GiB)...", flush=True)
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
                f"[Nier2iOS] Upload {name}: {status.progress() * 100:.1f}%",
                flush=True,
            )
    size = path.stat().st_size
    if int(result.get("size", -1)) != size:
        fail(f"Drive upload size mismatch for {name}")
    elapsed = max(time.monotonic() - started, 0.001)
    print(
        f"[Nier2iOS] Upload verificado: {name} — {size:,} bytes em {elapsed:.1f}s "
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
        "--exclude=./extract/*/RomFS.original.img",
        "--exclude=./extract/*/RomFS.original.img.id",
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
    print("[Nier2iOS] Verificando dependências locais do Colab...")

    # On Ubuntu/Colab the executable is `ninja`, but the APT package is
    # `ninja-build`. Passing `ninja` to apt-get fails with exit status 100.
    apt_command_packages = {
        "zstd": "zstd",
        "git": "git",
        "curl": "curl",
        "cmake": "cmake",
        "clang": "clang",
        "gcc": "gcc",
        "ninja": "ninja-build",
        "pkg-config": "pkg-config",
    }
    missing_commands = [
        package for executable, package in apt_command_packages.items()
        if shutil.which(executable) is None
    ]

    def apt_package_installed(name: str) -> bool:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${db:Status-Status}", name],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "installed"

    apt_packages = ("build-essential", "libssl-dev", "zlib1g-dev")
    missing_packages = [name for name in apt_packages if not apt_package_installed(name)]
    missing_apt = list(dict.fromkeys([*missing_commands, *missing_packages]))
    if missing_apt:
        print("[Nier2iOS] Instalando pacotes ausentes:", ", ".join(missing_apt))
        subprocess.run(["apt-get", "update", "-qq"], check=True)
        subprocess.run([
            "apt-get", "install", "-y", "--no-install-recommends", *missing_apt,
        ], check=True, env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"})
        missing_after_install = [
            exe for exe in apt_command_packages if shutil.which(exe) is None
        ]
        if missing_after_install:
            fail("APT completed but required executables are still missing: "
                 + ", ".join(missing_after_install))
    else:
        print("[Nier2iOS] Dependências APT já instaladas; pulando apt-get update/install.")

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
        print("[Nier2iOS] Instalando módulos Python ausentes:", ", ".join(packages))
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-q", *packages,
        ], check=True)
    else:
        print("[Nier2iOS] Módulos Python já instalados; pulando pip install.")

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
        print("[Nier2iOS] .NET 10 já instalado; pulando download/instalação.")

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
    print("[Nier2iOS] .NET 10 validado para apphost x64:")
    print(runtimes.strip())



def prepare(args, api=None) -> dict:
    # Fail early on a code error: never spend Colab disk/network on multi-GB
    # NSP downloads before checking the exact source of the handoff stages.
    checkout = Path(__file__).resolve().parents[2]
    code = [
        checkout / "nier/port_stages.py",
        checkout / "nier/colab/prepare_linux.py",
        checkout / "nier/colab/fast_shader_split.py",
        checkout / "nier/colab/source_archive.py",
        checkout / "nier/drive_chunks.py",
        checkout / "nier/scripts/mac_capture.py",
        checkout / "nier/scripts/build_shared.py",
        checkout / "nier/scripts/prepare_actions.py",
    ]
    subprocess.run([sys.executable, "-m", "py_compile", *map(str, code)], check=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover",
                    "-s", str(checkout / "nier/tests"),
                    "-p", "test_port_stages.py", "-v"], check=True)
    print("[Nier2iOS] Source and Linux/Mac handoff regressions verified "
          "before NSP download.", flush=True)
    for module_name, name in (("googleapiclient.discovery", "google-api-python-client"),
                              ("google.auth", "google-auth"), ("requests", "requests")):
        try:
            found = importlib.util.find_spec(module_name)
        except (ImportError, ValueError, ModuleNotFoundError):
            found = None
        if found is None:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", name], check=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    # A prior, failed notebook call may have cached prepare_linux in sys.modules.
    # Reload the latest source after the branch is updated, without removing
    # NSPs, RomFS, partial rewrite outputs or any shader cache.
    import prepare_linux
    importlib.reload(prepare_linux)
    run_preparation = prepare_linux.run_preparation
    from source_archive import prepare_source
    api = api or drive_api()
    root = Path("/content/nier")
    root.mkdir(parents=True, exist_ok=True)
    source = prepare_source(api, args.drive_folder_id, root)
    if source["package_count"] < 3 or source["update_nsp_count"] != 1 or source["dlc_nsp_count"] < 1:
        fail("NieR:Automata requires one base XCI, one update NSP and DLC NSP(s)")
    install_linux_dependencies(root)
    nx = root / "NX2Apple"
    checkout_ready = ((nx / ".git").exists()
                      and (nx / "tools" / "engine.py").is_file()
                      and (nx / ".upstream-ref").is_file())
    if checkout_ready and (nx / ".upstream-ref").read_text().strip() != ENGINE_PIN:
        # Only the engine checkout is re-cloned: never remove input-packages,
        # keys, prepared work/, existing RomFS or Drive checkpoints.
        print("[Nier2iOS] Pin changed; replacing only the stale engine checkout.", flush=True)
        shutil.rmtree(nx)
        checkout_ready = False
    if not checkout_ready:
        if nx.exists():
            shutil.rmtree(nx)
        print("[Nier2iOS] Cloning the fork's pinned engine/patch sources...", flush=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH,
                        f"https://github.com/{REPO}.git", str(nx)], check=True)
    else:
        # A resumed Colab may have the game cache from an older Nier2iOS commit.
        # Refresh only the source checkout, preserving input NSPs, keys and work/.
        subprocess.run(["git", "-C", str(nx), "fetch", "--depth", "1",
                        "origin", BRANCH], check=True)
        cached_head = subprocess.check_output(
            ["git", "-C", str(nx), "rev-parse", "HEAD"], text=True).strip()
        remote_head = subprocess.check_output(
            ["git", "-C", str(nx), "rev-parse", "FETCH_HEAD"], text=True).strip()
        if cached_head != remote_head:
            print(f"[Nier2iOS] Refreshing source {cached_head[:12]} -> {remote_head[:12]} "
                  "without deleting source game cache.", flush=True)
            subprocess.run(["git", "-C", str(nx), "reset", "--hard", "FETCH_HEAD"], check=True)
    if (nx / ".upstream-ref").read_text().strip() != ENGINE_PIN:
        fail("Nier2iOS checkout points to another NXNative commit")

    # engine.py check builds an extra scratch worktree before materialization.
    # On the Colab Python 3.13/Linux runtime it can return 1 with no engine/
    # produced. Sync itself applies every patch; 'stale' validates the resulting
    # pin, patch-series digest and generated commit. Avoid repeating an
    # expensive pre-sync check, and heal partial previous attempts.
    engine_tool = nx / "tools" / "engine.py"
    def engine_command(command: str, *options: str, accepted=(0,)) -> int:
        argv = [sys.executable, str(engine_tool), command, *options]
        print("[Nier2iOS] +", " ".join(argv), flush=True)
        result = subprocess.run(argv, cwd=nx, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", check=False)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
        log_suffix = "".join("-" + option.removeprefix("--") for option in options)
        (root / f"engine-{command}{log_suffix}.log").write_text(
            result.stdout + f"\nexit={result.returncode}\n", encoding="utf-8")
        if result.returncode not in accepted:
            fail(f"NXNative engine {command} failed (exit {result.returncode}). "
                 f"Diagnostic: {root / ('engine-' + command + '.log')}\n"
                 + result.stdout[-5000:])
        return result.returncode

    if engine_command("stale", accepted=(0, 1)) == 1:
        print("[Nier2iOS] Engine not yet materialized or stale: "
              "syncing all fork patches now, without touching game input cache.", flush=True)
        engine_command("sync")
    else:
        print("[Nier2iOS] Exact NXNative engine + fork patch queue already materialized; reusing.", flush=True)
    engine_command("stale")
    required_builder_files = (
        nx / "engine" / "scripts" / "build_ipa_from_nsp.py",
        nx / "engine" / "dm" / "games" / "profile_guess.py",
    )
    missing_builder_files = [p for p in required_builder_files if not p.is_file()]
    if missing_builder_files:
        # A stale stamp alone is not sufficient after a partial checkout,
        # interrupted disk write, or manual cleanup. Retry only engine/;
        # preserve the NSP, extracted game files, keys and work cache.
        print("[Nier2iOS] Engine stamp exists, but builder files are absent: "
              + ", ".join(map(str, missing_builder_files)), flush=True)
        print("[Nier2iOS] Repairing materialized engine with sync --force ...", flush=True)
        engine_command("sync", "--force")
        engine_command("stale")
        missing_builder_files = [p for p in required_builder_files if not p.is_file()]
        if missing_builder_files:
            fail("NXNative builder is still missing after forced sync: "
                 + ", ".join(map(str, missing_builder_files))
                 + ". See " + str(root / "engine-sync-force.log"))
    print("[Nier2iOS] Engine materialized and verified: "
          + str(required_builder_files[0]), flush=True)
    work = root / "work"
    prep = run_preparation(argparse.Namespace(nx2apple_root=nx, nsp_dir=Path(source["package_dir"]),
        keys=Path(source["keys_path"]), work_dir=work, translation_zip=Path(source["translation_zip"])))
    if (prep["title_id"] != TITLE_ID
            or not re.fullmatch(r"v[1-9][0-9]*", prep["package_version"])
            or prep.get("input_package_count") != source["package_count"] or prep.get("input_update_count") != 1 or prep.get("input_dlc_nsp_count") != source["dlc_nsp_count"] or prep.get("input_dlc_count", 0) < 1 or not prep.get("translation", {}).get("file_count")):
        fail("NXNative did not extract the correct game and update")
    romfs = work / prep["romfs_relative_path"]
    if not romfs.is_file() or romfs.stat().st_size == 0:
        fail("RomFS missing or empty")
    aoc_entries = prep.get("aoc_images", [])
    aoc_actual = sorted(x.name for x in (work / "aoc").glob("*.img"))
    if sorted(item["name"] for item in aoc_entries) != aoc_actual:
        fail("NXNative AOC inventory changed since Linux preparation")
    request_id = str(uuid.uuid4())
    output_id = create_folder(api, f"Nier2iOS_NieRAutomata_{request_id[:8]}", source["game_folder_id"])
    pipeline_id = create_folder(api, "pipeline", output_id)
    game_id = create_folder(api, TITLE_ID, create_folder(api, "games", output_id))
    print("[Nier2iOS] Enviando RomFS externa (a IPA não a incorporará).")
    romfs_record = upload_drive_file(api, romfs, game_id, "romfs.img")
    # NXNative may require shader content from more than one program version.
    # Keep *every* needed merged image available to the Mac host, without
    # copying any NSP, key or extra RomFS into the eventual iOS IPA.
    shader_romfs = []
    for shader_version in prep["shader_versions"]:
        if shader_version == prep["package_version"]:
            continue
        if re.fullmatch(r"v[0-9]+", shader_version) is None:
            fail(f"Unexpected shader version marker: {shader_version!r}")
        other = work / "extract" / shader_version / "RomFS.img"
        if not other.is_file() or other.stat().st_size <= 0:
            fail(f"NXNative source shader RomFS missing: {other}")
        item = upload_drive_file(api, other, game_id, f"romfs-{shader_version}.img")
        shader_romfs.append({"version": shader_version, **item})
    aoc_records = []
    if aoc_entries:
        aoc_folder_id = create_folder(api, "aoc", game_id)
        for item in aoc_entries:
            aoc_image = work / "aoc" / item["name"]
            if not aoc_image.is_file() or aoc_image.stat().st_size != item["size"]:
                fail(f"AOC image differs from Linux provenance: {item['name']}")
            aoc_records.append(upload_drive_file(api, aoc_image, aoc_folder_id, item["name"]))
    archive = root / "nier-work.tar.zst"
    build_work_archive(work, archive)
    archive_record = upload_drive_file(api, archive, pipeline_id, archive.name)
    handoff = {
        "format": 1, "project": "Nier2iOS", "branch": BRANCH,
        "request_id": request_id, "title_id": TITLE_ID,
        "package_version": prep["package_version"], "source_ref": NX2APPLE_REF,
        "source_files": source["source_files"],
        "engine_pin": ENGINE_PIN,
        "source_commit": subprocess.check_output(["git", "-C", str(nx), "rev-parse", "HEAD"], text=True).strip(),
        "drive_output_folder_id": output_id,
        "drive_output_folder_url": f"https://drive.google.com/drive/folders/{output_id}",
        "work_archive": archive_record, "game_data": {
            "folder_id": game_id,
            "folder_url": f"https://drive.google.com/drive/folders/{game_id}",
            "romfs": romfs_record, "shader_romfs": shader_romfs, "aoc": aoc_records,
            "romfs_relative_path": prep["romfs_relative_path"],
        },
        "prepared": prep, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    path = Path("/content/nier-handoff.json")
    path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    upload_drive_file(api, path, output_id, "handoff.json")
    print("[Nier2iOS] PREPARAÇÃO E UPLOAD VERIFICADOS.")
    print("Title ID:", TITLE_ID, "| graphics:", prep["graphics"], "| provisional:", prep["provisional"])
    print("Linux shader stage:", prep["shader_split_stage"],
          "| Native-only Mac stages:", ", ".join(prep["mac_host_stages"]) or "none")
    print("[Nier2iOS] Extract/merge/rewrite already saved on Drive; "
          "the Mac runner will handle only required native capture/Metal/Xcode.", flush=True)
    print("RomFS:", romfs_record["size"], "bytes")
    print("Additional shader-version RomFS images:", len(shader_romfs),
          "(verified on Drive, never included in IPA)")
    print("Prepared archive:", archive_record["size"], "bytes")
    print("Recovery folder:", handoff["drive_output_folder_url"])
    print("O notebook publica este handoff automaticamente na próxima fase.")
    return handoff


def recover(args, api=None) -> dict | None:
    from googleapiclient.http import MediaIoBaseDownload
    api = api or drive_api()
    game_folders = [x for x in list_children(api, args.drive_folder_id)
                    if x["name"].casefold() == "nier"
                    and x.get("mimeType") == "application/vnd.google-apps.folder"]
    if len(game_folders) != 1:
        fail("A pasta nier não foi encontrada na pasta compartilhada.")
    run_folders = [x for x in list_children(api, game_folders[0]["id"])
                   if x.get("mimeType") == "application/vnd.google-apps.folder"
                   and x["name"].startswith("Nier2iOS_NieRAutomata_")]
    run_folders.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)
    for folder in run_folders:
        items = [x for x in list_children(api, folder["id"]) if x["name"] == "handoff.json"]
        if len(items) != 1:
            continue
        path = Path("/content/nier-handoff.json")
        # Handoff recovery uses the same chunk/MD5-verified transfer.
        download_drive_file(api, items[0], path)
        try:
            d = json.loads(path.read_text())
        except (ValueError, OSError):
            path.unlink(missing_ok=True)
            continue
        p = d.get("prepared", {})
        if not (d.get("project") == "Nier2iOS" and d.get("branch") == BRANCH
                and d.get("title_id") == TITLE_ID and d.get("package_version") == p.get("package_version")
                and d.get("package_version") == "v131072"
                and p.get("translation", {}).get("zip_sha256") == d.get("source_files", {}).get("translation", {}).get("sha256")
                and p.get("translation", {}).get("sha256") == d.get("game_data", {}).get("romfs", {}).get("sha256")
                and p.get("input_package_count", 0) >= 3 and p.get("input_update_count") == 1 and p.get("input_dlc_count", 0) > 0 and p.get("translation", {}).get("file_count", 0) > 0
                 and all(re.fullmatch(r"[0-9a-f]{64}", d.get("source_files", {}).get(k, {}).get("sha256", ""))
                         for k in ("base", "update"))
                and len(d.get("source_files", {}).get("dlcs", [])) == p.get("input_dlc_nsp_count")
                and d.get("engine_pin") == ENGINE_PIN
                and d.get("work_archive", {}).get("id")
                and d.get("game_data", {}).get("romfs", {}).get("id")
                and len(d.get("game_data", {}).get("aoc", [])) == len(p.get("aoc_images", []))
                and p.get("graphics") in ("nvn", "gl", "vulkan")):
            path.unlink(missing_ok=True)
            continue
        print("[Nier2iOS] Recuperado sem baixar NSP nem refazer a preparação:", d["request_id"])
        return d
    print("[Nier2iOS] Nenhuma preparação verificada foi encontrada. Execute a primeira preparação.")
    return None


def dispatch(args) -> None:
    import requests
    path = args.handoff.resolve()
    if not path.is_file():
        fail(f"Handoff ausente: {path}")
    d = json.loads(path.read_text())
    if d.get("project") != "Nier2iOS" or d.get("branch") != BRANCH or d.get("title_id") != TITLE_ID:
        fail("Handoff pertence a outro projeto ou jogo")
    # Colab notebook getpass must execute in the notebook kernel, not a child process.
    token = os.environ.get("NIER_GITHUB_TOKEN", "").strip()
    if not token:
        token = getpass.getpass("Fine-grained GitHub PAT (Contents: Read and write; KintTany): ").strip()
    if not token:
        fail("GitHub token vazio")
    url = f"https://api.github.com/repos/{REPO}/contents/nier/handoff.json"
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
    body = {"message": f"Nier2iOS NieR:Automata: build request {d['request_id'][:8]}",
            "content": base64.b64encode((json.dumps(d, indent=2) + "\n").encode()).decode(),
            "branch": BRANCH}
    if old.status_code == 200:
        body["sha"] = old.json()["sha"]
    response = requests.put(url, headers=headers, json=body, timeout=60)
    if response.status_code not in (200, 201):
        fail(f"GitHub PUT falhou: {response.status_code} {response.text[:300]}")
    print("[Nier2iOS] One handoff commit triggers only one Nier2iOS workflow.")
    print("Commit:", response.json().get("commit", {}).get("html_url"))
    print("Actions:", f"https://github.com/{REPO}/actions")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nier2iOS NieR:Automata - Colab to Drive to Actions")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("prepare", prepare), ("recover", recover)):
        p = sub.add_parser(name)
        p.add_argument("--drive-folder-id", default="19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm")
        p.set_defaults(func=handler)
    p = sub.add_parser("dispatch")
    p.add_argument("--handoff", type=Path, default=Path("/content/nier-handoff.json"))
    p.set_defaults(func=dispatch)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
