#!/usr/bin/env python3
"""Fetch and extract the BOTW source RAR in Colab; retain only NSPs in Drive."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath

FOLDER_MIME = "application/vnd.google-apps.folder"
CHUNK = 64 * 1024 * 1024


def fail(message: str) -> None:
    raise SystemExit("[Link2iOS] ERROR: " + message)


def list_children(api, parent_id: str) -> list[dict]:
    files, token = [], None
    while True:
        page = api.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000,
            pageToken=token,
            orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,modifiedTime)",
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


def download_rar(url: str, target: Path) -> None:
    import requests

    if not url.startswith(("https://", "http://")):
        fail("o link de download está vazio ou inválido.")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".rar.part")
    total = 0
    last_report = 0
    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=(30, 180)) as response:
            if response.status_code >= 400:
                fail(f"o servidor do arquivo respondeu HTTP {response.status_code}; verifique se o link ainda está válido.")
            expected = int(response.headers.get("content-length") or 0)
            with partial.open("wb") as output:
                for block in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if not block:
                        continue
                    output.write(block)
                    total += len(block)
                    if total - last_report >= 512 * 1024 * 1024:
                        if expected:
                            print(f"[Link2iOS] Download: {total / 1024**3:.2f}/{expected / 1024**3:.2f} GiB")
                        else:
                            print(f"[Link2iOS] Download: {total / 1024**3:.2f} GiB")
                        last_report = total
        if total < 8:
            fail("o arquivo recebido está vazio ou incompleto.")
        with partial.open("rb") as stream:
            signature = stream.read(7)
        if not signature.startswith(b"Rar!\x1a\x07"):
            fail("o link não retornou um arquivo RAR válido; pode ter expirado ou retornado uma página de erro.")
        partial.replace(target)
        print(f"[Link2iOS] RAR baixado: {total:,} bytes.")
    except SystemExit:
        partial.unlink(missing_ok=True)
        raise
    except Exception:
        partial.unlink(missing_ok=True)
        fail("falha ao baixar o RAR. Verifique a validade do link e tente novamente; o link assinado não será exibido no log.")


def extract_rar(archive: Path, destination: Path, sevenzip: str) -> None:
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
            fail(f"o RAR contém caminho inseguro e não será extraído: {raw}")
    if "Symbolic Link =" in listing or "Hard Link =" in listing:
        fail("o RAR contém links simbólicos/duros; a extração foi interrompida.")
    tested = subprocess.run([sevenzip, "t", str(archive)], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
    if tested.returncode:
        fail("o 7-Zip detectou RAR danificado, incompleto ou protegido por senha.")
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    extracted = subprocess.run(
        [sevenzip, "x", str(archive), f"-o{destination}", "-y"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if extracted.returncode:
        fail("falha ao extrair o RAR: " + extracted.stdout[-2000:])
    print("[Link2iOS] RAR validado e extraído no armazenamento temporário do Colab.")


def drive_key(api, root_id: str) -> dict | None:
    children = list_children(api, root_id)
    key = next((item for item in children
                if item.get("mimeType") != FOLDER_MIME and item.get("name", "").lower() == "prod.keys"), None)
    if key:
        return key
    key_folder = next((item for item in children
                       if item.get("mimeType") == FOLDER_MIME and item.get("name", "").lower() == "keys"), None)
    if key_folder:
        return next((item for item in list_children(api, key_folder["id"])
                     if item.get("mimeType") != FOLDER_MIME and item.get("name", "").lower() == "prod.keys"), None)
    return None


def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    with partial.open("wb") as output:
        downloader = MediaIoBaseDownload(output, request, chunksize=CHUNK)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"[Link2iOS] Drive {item['name']}: {status.progress() * 100:.1f}%")
    expected = int(item.get("size") or 0)
    if expected and partial.stat().st_size != expected:
        partial.unlink(missing_ok=True)
        fail(f"tamanho incorreto ao baixar {item['name']} do Drive.")
    partial.replace(destination)


def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            chunksize=CHUNK, resumable=True)
    item = api.files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id,name,size",
        supportsAllDrives=True,
    ).execute()
    size = path.stat().st_size
    if int(item.get("size", -1)) != size:
        fail(f"tamanho incorreto após enviar {name} ao Drive.")
    print(f"[Link2iOS] NSP extraído salvo no Drive: {name} ({size:,} bytes)")
    return {"id": item["id"], "name": item["name"], "size": size}


def existing_extracted_folder(api, root_id: str) -> tuple[dict, list[dict]] | None:
    folders = [item for item in list_children(api, root_id)
               if item.get("mimeType") == FOLDER_MIME
               and item.get("name", "").lower().startswith("botw_extracted")]
    folders.sort(key=lambda item: item.get("modifiedTime", ""), reverse=True)
    for folder in folders:
        nsps = [item for item in list_children(api, folder["id"])
                if item.get("mimeType") != FOLDER_MIME
                and item.get("name", "").lower().endswith(".nsp")]
        if nsps:
            return folder, nsps
    return None


def prepare_source(api, drive_folder_id: str, runtime_root: Path) -> dict:
    """Reuse the flattened NSP folder or download/extract the provided RAR once."""
    from googleapiclient.http import MediaIoBaseDownload  # noqa: F401

    local_nsp_dir = runtime_root / "input-nsps"
    local_keys = runtime_root / "keys" / "prod.keys"
    shutil.rmtree(local_nsp_dir, ignore_errors=True)
    local_nsp_dir.mkdir(parents=True, exist_ok=True)
    local_keys.parent.mkdir(parents=True, exist_ok=True)

    key_item = drive_key(api, drive_folder_id)
    if key_item is None:
        fail("prod.keys não foi encontrado na raiz da pasta do Drive. Coloque prod.keys ao lado do link/pasta BOTW e execute novamente.")
    download_drive_file(api, key_item, local_keys)

    existing = existing_extracted_folder(api, drive_folder_id)
    if existing:
        folder, items = existing
        print(f"[Link2iOS] Reutilizando NSPs já extraídos do Drive: {folder['name']}")
        for index, item in enumerate(items, start=1):
            local = local_nsp_dir / f"{index:03d}_{safe_name(item['name'])}"
            download_drive_file(api, item, local)
        return {
            "nsp_dir": str(local_nsp_dir), "keys_path": str(local_keys),
            "source_folder_id": folder["id"], "source_folder_name": folder["name"],
            "nsp_count": len(items), "source_reused": True,
        }

    url = os.environ.get("LINK2IOS_DOWNLOAD_URL", "").strip()
    if not url:
        fail("a pasta ainda não tem BOTW_Extracted. Cole o link assinado do RAR no campo protegido do notebook.")
    temp_root = runtime_root / "rar-temporary"
    archive = temp_root / "botw.rar"
    extracted = temp_root / "extracted"
    shutil.rmtree(temp_root, ignore_errors=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        download_rar(url, archive)
        sevenzip = install_7zip()
        extract_rar(archive, extracted, sevenzip)
        nsps = sorted(path for path in extracted.rglob("*")
                      if path.is_file() and path.suffix.lower() == ".nsp")
        if not nsps:
            fail("o RAR foi extraído, mas não contém nenhum arquivo .nsp.")
        folder_name = "BOTW_Extracted"
        occupied = {item.get("name", "").lower()
                    for item in list_children(api, drive_folder_id)
                    if item.get("mimeType") == FOLDER_MIME}
        if folder_name.lower() in occupied:
            folder_name = f"BOTW_Extracted_{time.strftime('%Y%m%d_%H%M%S')}"
        folder = create_folder(api, folder_name, drive_folder_id)
        print(f"[Link2iOS] Enviando {len(nsps)} NSP(s) extraídos para o Drive...")
        for index, source in enumerate(nsps, start=1):
            filename = f"{index:03d}_{safe_name(source.name)}"
            local = local_nsp_dir / filename
            shutil.copy2(source, local)
            upload_drive_file(api, local, folder["id"], filename)
        print("[Link2iOS] Somente NSPs extraídos foram mantidos no Drive; prod.keys permanece na raiz.")
        return {
            "nsp_dir": str(local_nsp_dir), "keys_path": str(local_keys),
            "source_folder_id": folder["id"], "source_folder_name": folder_name,
            "nsp_count": len(nsps), "source_reused": False,
        }
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(extracted, ignore_errors=True)
        shutil.rmtree(temp_root, ignore_errors=True)
