#!/usr/bin/env python3
"""Fetch a DMC2 base-game 7z archive, extract its XCI or NSP, and stage update/DLC NSPs."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath

FOLDER_MIME = "application/vnd.google-apps.folder"
CHUNK = 64 * 1024 * 1024
SEVEN_Z_SIGNATURE = bytes.fromhex("377abcaf271c")


def fail(message: str) -> None:
    raise SystemExit("[Dante2iOS] ERROR: " + message)


def list_children(api, parent_id: str) -> list[dict]:
    files, token = [], None
    while True:
        page = api.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000,
            pageToken=token,
            orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,modifiedTime,md5Checksum)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files.extend(page.get("files", []))
        token = page.get("nextPageToken")
        if not token:
            return files


def safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return name or "game.nsp"


def create_folder(api, name: str, parent_id: str) -> dict:
    return api.files().create(
        body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        fields="id,name",
        supportsAllDrives=True,
    ).execute()


def install_7zip() -> str:
    binary = shutil.which("7z") or shutil.which("7zz")
    if binary:
        return binary
    subprocess.run(["apt-get", "update", "-qq"], check=True)
    for package in ("p7zip-full", "7zip"):
        result = subprocess.run(
            ["apt-get", "install", "-y", "-qq", package],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        binary = shutil.which("7z") or shutil.which("7zz")
        if result.returncode == 0 and binary:
            return binary
    fail("não foi possível instalar o extrator 7-Zip no Colab.")
    raise AssertionError("unreachable")


def download_7z(url: str, target: Path) -> None:
    import requests

    if not url.startswith(("https://", "http://")):
        fail("o link assinado do 7z está vazio ou inválido.")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".7z.part")
    total = 0
    last_report = 0
    started = time.monotonic()
    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=(30, 180)) as response:
            if response.status_code >= 400:
                fail(f"o servidor do 7z respondeu HTTP {response.status_code}; o link pode ter expirado.")
            expected = int(response.headers.get("content-length") or 0)
            with partial.open("wb") as output:
                for block in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if not block:
                        continue
                    output.write(block)
                    total += len(block)
                    if total - last_report >= 512 * 1024 * 1024:
                        if expected:
                            print(f"[Dante2iOS] Download 7z: {total / 1024**3:.2f}/{expected / 1024**3:.2f} GiB")
                        else:
                            print(f"[Dante2iOS] Download 7z: {total / 1024**3:.2f} GiB")
                        last_report = total
        if total < 32:
            fail("o arquivo recebido está vazio ou incompleto.")
        with partial.open("rb") as stream:
            signature = stream.read(len(SEVEN_Z_SIGNATURE))
        if signature != SEVEN_Z_SIGNATURE:
            fail("o link não retornou um arquivo 7z válido; pode ter expirado ou retornado uma página de erro.")
        partial.replace(target)
        elapsed = max(time.monotonic() - started, 0.001)
        print(
            f"[Dante2iOS] 7z concluído: {total:,} bytes "
            f"({total / 1024**3:.2f} GiB) em {elapsed:.1f}s; "
            f"média {total / elapsed / 1024**2:.1f} MiB/s."
        )
    except SystemExit:
        partial.unlink(missing_ok=True)
        raise
    except Exception:
        partial.unlink(missing_ok=True)
        fail("falha ao baixar o 7z. Verifique a validade do link; a URL assinada não será exibida no log.")


def validate_xci(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 0x104:
        fail(f"XCI vazio ou truncado: {path.name}")
    with path.open("rb") as stream:
        stream.seek(0x100)
        magic = stream.read(4)
    if magic != b"HEAD":
        fail(f"{path.name} não tem o cabeçalho XCI esperado (HEAD no offset 0x100).")


def validate_nsp(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 4:
        fail(f"NSP vazio ou truncado: {path.name}")
    with path.open("rb") as stream:
        magic = stream.read(4)
    if magic != b"PFS0":
        fail(f"{path.name} não tem o cabeçalho NSP esperado (PFS0 no offset 0).")


def validate_base_package(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".xci":
        validate_xci(path)
        return "XCI"
    if suffix == ".nsp":
        validate_nsp(path)
        return "NSP"
    fail(f"formato de pacote base não suportado: {path.name}")
    raise AssertionError("unreachable")


def extract_7z(archive: Path, destination: Path, sevenzip: str) -> None:
    listing = subprocess.run(
        [sevenzip, "l", "-slt", str(archive)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    ).stdout
    for line in listing.splitlines():
        if not line.startswith("Path = "):
            continue
        raw = line[len("Path = "):].strip()
        if raw == str(archive) or raw == archive.name:
            continue
        normalized = raw.replace("\\", "/")
        member = PurePosixPath(normalized)
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ".." in member.parts:
            fail(f"o 7z contém caminho inseguro e não será extraído: {raw}")
    if "Symbolic Link =" in listing or "Hard Link =" in listing:
        fail("o 7z contém links simbólicos/duros; a extração foi interrompida.")
    print("[Dante2iOS] Testando integridade do 7z...")
    tested = subprocess.run(
        [sevenzip, "t", str(archive)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if tested.returncode:
        fail("o 7-Zip detectou arquivo danificado, incompleto ou protegido por senha.")
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    print("[Dante2iOS] Extraindo o pacote base do 7z; esta etapa depende do tamanho e da velocidade do armazenamento...")
    extracted = subprocess.run(
        [sevenzip, "x", str(archive), f"-o{destination}", "-y"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if extracted.returncode:
        fail("falha ao extrair o 7z: " + extracted.stdout[-2000:])
    files = [p for p in destination.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    print(
        f"[Dante2iOS] Extração concluída: {len(files)} arquivo(s), "
        f"{total_bytes:,} bytes ({total_bytes / 1024**3:.2f} GiB) extraídos."
    )


def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = int(item.get("size") or 0)
    expected_md5 = str(item.get("md5Checksum") or "").lower()
    if destination.is_file() and expected and destination.stat().st_size == expected:
        if expected_md5:
            digest = hashlib.md5()
            with destination.open("rb") as stream:
                for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest().lower() == expected_md5:
                print(f"[Dante2iOS] Reutilizando {item['name']}: {expected:,} bytes verificados (MD5 Drive).")
                return
        else:
            print(f"[Dante2iOS] Reutilizando {item['name']}: {expected:,} bytes (tamanho conferido).")
            return
    partial = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    started = time.monotonic()
    with partial.open("wb") as output:
        downloader = MediaIoBaseDownload(output, request, chunksize=CHUNK)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"[Dante2iOS] Drive {item['name']}: {status.progress() * 100:.1f}%")
    if expected and partial.stat().st_size != expected:
        partial.unlink(missing_ok=True)
        fail(f"tamanho incorreto ao baixar {item['name']} do Drive.")
    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        fail(f"o arquivo {item['name']} baixado do Drive está vazio.")
    partial.replace(destination)
    elapsed = max(time.monotonic() - started, 0.001)
    size = destination.stat().st_size
    print(
        f"[Dante2iOS] Download concluído: {item['name']} — {size:,} bytes "
        f"({size / 1024**3:.2f} GiB), {elapsed:.1f}s, "
        f"{size / elapsed / 1024**2:.1f} MiB/s."
    )


def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            chunksize=CHUNK, resumable=True)
    request = api.files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id,name,size",
        supportsAllDrives=True,
    )
    item = None
    while item is None:
        status, item = request.next_chunk()
        if status:
            print(f"[Dante2iOS] Upload {name}: {status.progress() * 100:.1f}%", flush=True)
    size = path.stat().st_size
    if int(item.get("size", -1)) != size:
        fail(f"tamanho incorreto após enviar {name} ao Drive.")
    print(f"[Dante2iOS] Pacote base salvo no Drive: {name} ({size:,} bytes)")
    return {"id": item["id"], "name": item["name"], "size": size}



def prepare_source(api, drive_folder_id: str, runtime_root: Path) -> dict:
    """Stage exactly one DMC2 base NSP from the Drive/dmc2 folder. Never merge another game's sources."""
    root = list_children(api, drive_folder_id)
    folders = [x for x in root if x.get("mimeType") == FOLDER_MIME and x["name"].casefold() == "dmc2"]
    if len(folders) != 1:
        fail("A pasta compartilhada precisa conter exatamente uma subpasta chamada dmc2.")
    folder = folders[0]
    entries = list_children(api, folder["id"])
    # prod.keys is allowed in dmc2 or alongside it, but is never committed or packed.
    keys = [x for x in entries + root
            if x.get("mimeType") != FOLDER_MIME and x["name"].casefold() == "prod.keys"]
    if not keys:
        fail("prod.keys não localizado em dmc2 nem na raiz compartilhada.")
    key_item = keys[0]
    local_package_dir = runtime_root / "input-packages"
    local_package_dir.mkdir(parents=True, exist_ok=True)
    keys_path = runtime_root / "keys" / "prod.keys"
    keys_path.parent.mkdir(parents=True, exist_ok=True)
    download_drive_file(api, key_item, keys_path)

    # Accept an NSP directly in dmc2 or one child subfolder, or one 7z containing one NSP.
    candidates = [(folder, x) for x in entries
                  if x.get("mimeType") != FOLDER_MIME and x["name"].lower().endswith((".nsp", ".7z"))]
    for sub in [x for x in entries if x.get("mimeType") == FOLDER_MIME]:
        candidates += [(sub, x) for x in list_children(api, sub["id"])
                       if x.get("mimeType") != FOLDER_MIME and x["name"].lower().endswith((".nsp", ".7z"))]
    if len(candidates) != 1:
        fail("dmc2 deve conter exatamente um NSP base ou um 7z com o NSP base; "
             f"encontrados {len(candidates)} candidatos: {[x['name'] for _, x in candidates]}")
    base_folder, item = candidates[0]
    if item["name"].lower().endswith(".nsp"):
        local_base = local_package_dir / "000_base_dmc2.nsp"
        download_drive_file(api, item, local_base)
    else:
        archive = runtime_root / "7z-temporary" / "dmc2-base.7z"
        archive.parent.mkdir(parents=True, exist_ok=True)
        download_drive_file(api, item, archive)
        extracted = runtime_root / "7z-temporary" / "extracted"
        extract_7z(archive, extracted, install_7zip())
        nsps = sorted(p for p in extracted.rglob("*") if p.is_file() and p.suffix.lower() == ".nsp")
        if len(nsps) != 1:
            fail(f"Arquivo 7z deveria conter exatamente um NSP base, contém {len(nsps)}.")
        local_base = local_package_dir / "000_base_dmc2.nsp"
        if local_base.exists():
            local_base.unlink()
        shutil.copyfile(nsps[0], local_base)
    validate_nsp(local_base)
    for old in local_package_dir.iterdir():
        if old.is_file() and old != local_base and old.suffix.lower() in (".nsp", ".xci", ".nsz", ".xcz"):
            old.unlink()
    return {
        "package_dir": str(local_package_dir), "keys_path": str(keys_path),
        "package_count": 1, "base_type": "NSP",
        "update_nsp_count": 0, "dlc_nsp_count": 0,
        "source_folder_id": base_folder["id"], "source_folder_name": base_folder["name"],
        "game_folder_id": folder["id"], "original_name": item["name"],
    }
