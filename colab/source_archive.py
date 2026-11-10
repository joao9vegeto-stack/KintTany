#!/usr/bin/env python3
"""Fetch a BOTW base-game 7z archive, extract its XCI, and stage update/DLC NSPs."""
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
    raise SystemExit("[Link2iOS] ERROR: " + message)


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
    return name or "game.xci"


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
                            print(f"[Link2iOS] Download 7z: {total / 1024**3:.2f}/{expected / 1024**3:.2f} GiB")
                        else:
                            print(f"[Link2iOS] Download 7z: {total / 1024**3:.2f} GiB")
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
            f"[Link2iOS] 7z concluído: {total:,} bytes "
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
    print("[Link2iOS] Testando integridade do 7z...")
    tested = subprocess.run(
        [sevenzip, "t", str(archive)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if tested.returncode:
        fail("o 7-Zip detectou arquivo danificado, incompleto ou protegido por senha.")
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    print("[Link2iOS] Extraindo o XCI do 7z; esta etapa depende do tamanho e da velocidade do armazenamento...")
    extracted = subprocess.run(
        [sevenzip, "x", str(archive), f"-o{destination}", "-y"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if extracted.returncode:
        fail("falha ao extrair o 7z: " + extracted.stdout[-2000:])
    files = [p for p in destination.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    print(
        f"[Link2iOS] Extração concluída: {len(files)} arquivo(s), "
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
                print(f"[Link2iOS] Reutilizando {item['name']}: {expected:,} bytes verificados (MD5 Drive).")
                return
        else:
            print(f"[Link2iOS] Reutilizando {item['name']}: {expected:,} bytes (tamanho conferido).")
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
                print(f"[Link2iOS] Drive {item['name']}: {status.progress() * 100:.1f}%")
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
        f"[Link2iOS] Download concluído: {item['name']} — {size:,} bytes "
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
            print(f"[Link2iOS] Upload {name}: {status.progress() * 100:.1f}%", flush=True)
    size = path.stat().st_size
    if int(item.get("size", -1)) != size:
        fail(f"tamanho incorreto após enviar {name} ao Drive.")
    print(f"[Link2iOS] XCI base salvo no Drive: {name} ({size:,} bytes)")
    return {"id": item["id"], "name": item["name"], "size": size}


def existing_base_folder(api, root_id: str) -> tuple[dict, dict] | None:
    folders = [item for item in list_children(api, root_id)
               if item.get("mimeType") == FOLDER_MIME
               and item.get("name", "").lower().startswith("botw_base_xci")]
    folders.sort(key=lambda item: item.get("modifiedTime", ""), reverse=True)
    for folder in folders:
        xcis = [item for item in list_children(api, folder["id"])
                if item.get("mimeType") != FOLDER_MIME
                and item.get("name", "").lower().endswith(".xci")]
        if len(xcis) == 1:
            return folder, xcis[0]
    return None


def prepare_source(api, drive_folder_id: str, runtime_root: Path) -> dict:
    """Reuse the extracted base XCI and cached package downloads across notebook retries."""
    local_package_dir = runtime_root / "input-packages"
    local_keys = runtime_root / "keys" / "prod.keys"
    # Keep already downloaded inputs in this Colab runtime. download_drive_file
    # reuses matching Drive sizes/MD5 instead of transferring the same multi-GB files again.
    local_package_dir.mkdir(parents=True, exist_ok=True)
    local_keys.parent.mkdir(parents=True, exist_ok=True)

    root_items = list_children(api, drive_folder_id)
    key_item = next((item for item in root_items
                     if item.get("mimeType") != FOLDER_MIME
                     and item.get("name", "").lower() == "prod.keys"), None)
    if key_item is None:
        fail("prod.keys não foi encontrado na raiz da pasta compartilhada.")

    dlc_items = {}
    for expected in ("dlc1.nsp", "dlc2.nsp"):
        item = next((entry for entry in root_items
                     if entry.get("mimeType") != FOLDER_MIME
                     and entry.get("name", "").lower() == expected), None)
        if item is None:
            fail(f"{expected} não foi encontrado na raiz da pasta compartilhada.")
        dlc_items[expected] = item

    # Only these exact root-level NSP names are inputs. Ignore all other
    # files/folders created by Kleo2iOS or previous pipeline runs.
    update_item = next((entry for entry in root_items
                        if entry.get("mimeType") != FOLDER_MIME
                        and entry.get("name", "").lower() == "update.nsp"), None)
    if update_item is None:
        fail("update.nsp não foi encontrado na raiz da pasta compartilhada.")

    download_drive_file(api, key_item, local_keys)

    def add_root_packages() -> None:
        update_local = local_package_dir / f"001_update_{safe_name(update_item['name'])}"
        download_drive_file(api, update_item, update_local)
        print(f"[Link2iOS] Update NSP incluído: {update_item['name']}")
        for index, expected in enumerate(("dlc1.nsp", "dlc2.nsp"), start=1):
            item = dlc_items[expected]
            local = local_package_dir / f"00{index + 1}_{safe_name(item['name'])}"
            download_drive_file(api, item, local)
            print(f"[Link2iOS] DLC NSP incluído: {expected}")

    existing = existing_base_folder(api, drive_folder_id)
    if existing:
        folder, item = existing
        local_xci = local_package_dir / f"000_base_{safe_name(item['name'])}"
        download_drive_file(api, item, local_xci)
        validate_xci(local_xci)
        print(f"[Link2iOS] Reutilizando XCI base do Drive: {folder['name']}/{item['name']}")
        add_root_packages()
        return {
            "package_dir": str(local_package_dir), "keys_path": str(local_keys),
            "source_folder_id": folder["id"], "source_folder_name": folder["name"],
            "package_count": 4, "xci_count": 1, "nsp_count": 3,
            "update_nsp_count": 1, "dlc_nsp_count": 2, "source_reused": True,
        }

    url = os.environ.get("LINK2IOS_DOWNLOAD_URL", "").strip()
    if not url:
        fail("a pasta ainda não tem BOTW_Base_XCI. Cole o link assinado do 7z no campo protegido do notebook.")
    temp_root = runtime_root / "7z-temporary"
    archive = temp_root / "botw-base.7z"
    extracted = temp_root / "extracted"
    shutil.rmtree(temp_root, ignore_errors=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        download_7z(url, archive)
        sevenzip = install_7zip()
        extract_7z(archive, extracted, sevenzip)
        extracted_files = sorted(path for path in extracted.rglob("*") if path.is_file())
        xcis = [path for path in extracted_files if path.suffix.lower() == ".xci"]

        # Large Switch dumps are sometimes stored as contiguous split-XCI parts
        # (.xc0, .xc1, ...). 7-Zip extracts those as several files, not one .xci.
        # Reassemble only a single, unambiguous, gap-free sequence.
        if not xcis:
            split_groups: dict[str, list[tuple[int, Path]]] = {}
            for path in extracted_files:
                match = re.match(r"^(.*)\.xc(\d+)$", path.name, flags=re.IGNORECASE)
                if match:
                    split_groups.setdefault(match.group(1).lower(), []).append(
                        (int(match.group(2)), path)
                    )
            valid_groups = []
            for group_name, parts in split_groups.items():
                parts.sort(key=lambda item: item[0])
                indices = [index for index, _ in parts]
                if len(parts) >= 2 and indices == list(range(indices[0], indices[0] + len(indices))):
                    valid_groups.append((group_name, parts))
            if len(valid_groups) == 1:
                group_name, parts = valid_groups[0]
                source_xci = extracted / (parts[0][1].stem + ".xci")
                print(
                    f"[Link2iOS] XCI dividido detectado: {len(parts)} partes "
                    f"({', '.join(part.name for _, part in parts)}). Reconstituindo em disco..."
                )
                with source_xci.open("wb") as output:
                    for index, part in parts:
                        print(f"[Link2iOS] Unindo parte XC{index}: {part.stat().st_size:,} bytes")
                        with part.open("rb") as input_stream:
                            shutil.copyfileobj(input_stream, output, length=64 * 1024 * 1024)
                print(f"[Link2iOS] XCI reconstituído: {source_xci.stat().st_size:,} bytes.")
                xcis = [source_xci]
            elif len(valid_groups) > 1:
                fail("o 7z contém mais de um conjunto XCI dividido; não é possível escolher a base com segurança.")

        if len(xcis) != 1:
            listing = "; ".join(
                f"{path.relative_to(extracted).as_posix()} ({path.stat().st_size:,} bytes)"
                for path in extracted_files
            )
            fail(
                f"o 7z precisa conter um XCI único ou um conjunto .xc0/.xc1/... contínuo; "
                f"encontrados {len(xcis)} XCI(s). Arquivos extraídos: {listing or '(nenhum)'}."
            )
        source_xci = xcis[0]
        validate_xci(source_xci)

        folder_name = "BOTW_Base_XCI"
        occupied = {item.get("name", "").lower()
                    for item in list_children(api, drive_folder_id)
                    if item.get("mimeType") == FOLDER_MIME}
        if folder_name.lower() in occupied:
            folder_name = f"BOTW_Base_XCI_{time.strftime('%Y%m%d_%H%M%S')}"
        folder = create_folder(api, folder_name, drive_folder_id)
        filename = f"000_base_{safe_name(source_xci.name)}"
        local_xci = local_package_dir / filename
        shutil.copy2(source_xci, local_xci)
        upload_drive_file(api, local_xci, folder["id"], filename)
        add_root_packages()
        print("[Link2iOS] XCI base armazenado no Drive; update e DLC1/DLC2 são lidos diretamente da raiz.")
        return {
            "package_dir": str(local_package_dir), "keys_path": str(local_keys),
            "source_folder_id": folder["id"], "source_folder_name": folder_name,
            "package_count": 4, "xci_count": 1, "nsp_count": 3,
            "update_nsp_count": 1, "dlc_nsp_count": 2, "source_reused": False,
        }
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(extracted, ignore_errors=True)
        shutil.rmtree(temp_root, ignore_errors=True)
