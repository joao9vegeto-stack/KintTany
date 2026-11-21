#!/usr/bin/env python3
"""Colab-only Biomutant RAR ingestion: URL -> NSP -> verified Drive -> delete RAR.

Never run this in GitHub Actions. Large source packages and extraction are Linux work.
The supplied URLs may be temporary; only this notebook cell carries those URLs.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests
from googleapiclient.http import MediaFileUpload
from source_archive import GAME_FOLDER_ID, list_children

RAR_MAGIC = (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")
CHUNK = 16 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise RuntimeError("[BioiOSMutant RAR] " + message)


def file_hashes(path: Path):
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            md5.update(chunk)
            sha.update(chunk)
    return md5.hexdigest(), sha.hexdigest()


def download_rar(url: str, destination: Path):
    require(url.startswith("https://"), "Only HTTPS RAR download links are accepted")
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = Path(str(destination) + ".downloaded")
    if completed.is_file() and destination.is_file():
        with destination.open("rb") as existing:
            header = existing.read(8)
        if (any(header.startswith(magic) for magic in RAR_MAGIC)
                and completed.read_text().strip() == str(destination.stat().st_size)):
            print("[BioiOSMutant] Complete cached RAR found:", destination)
            return
    completed.unlink(missing_ok=True)
    # A partial file can be retried using Range. Validate the server's reply.
    for attempt in range(1, 6):
        size = destination.stat().st_size if destination.exists() else 0
        headers = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"}
        if size:
            headers["Range"] = f"bytes={size}-"
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(30, 180),
                              allow_redirects=True) as response:
                response.raise_for_status()
                if size and response.status_code == 206:
                    content_range = response.headers.get("Content-Range", "")
                    require(content_range.startswith(f"bytes {size}-"),
                            "Server returned an inconsistent resumed download range")
                    mode = "ab"
                else:
                    require(response.status_code == 200,
                            f"Unexpected RAR response {response.status_code}")
                    mode = "wb"
                total = int(response.headers.get("Content-Length", "0") or 0)
                written, prior = 0, -1
                with destination.open(mode) as output:
                    for data in response.iter_content(chunk_size=4 * 1024 * 1024):
                        if not data:
                            continue
                        output.write(data)
                        written += len(data)
                        if total:
                            pct = int(100 * written / total)
                            if pct // 10 != prior // 10:
                                prior = pct
                                print(f"[BioiOSMutant] {destination.name}: {pct}%", flush=True)
                require(total == 0 or written == total,
                        "Incomplete RAR body (download can be resumed)")
            with destination.open("rb") as verified:
                header = verified.read(8)
            require(any(header.startswith(m) for m in RAR_MAGIC),
                    "Link delivered HTML/other content, not a RAR; refresh the temporary URL")
            completed.write_text(str(destination.stat().st_size))
            return
        except (requests.RequestException, OSError) as error:
            if attempt == 5:
                raise RuntimeError(f"RAR download failed after {attempt} attempts: {error}") from error
            print(f"[BioiOSMutant] Retrying download {attempt}/5: {error}", flush=True)
            time.sleep(attempt * 2)


def sevenzip_executable() -> str:
    for name in ("7zz", "7z"):
        found = shutil.which(name)
        if found:
            return found
    subprocess.run(["apt-get", "update", "-qq"], check=True)
    try:
        subprocess.run(["apt-get", "install", "-y", "-qq", "7zip"], check=True)
    except subprocess.CalledProcessError:
        subprocess.run(["apt-get", "install", "-y", "-qq", "p7zip-full"], check=True)
    executable = shutil.which("7zz") or shutil.which("7z")
    require(executable, "7-Zip is unavailable in this Linux runtime")
    return executable


def extract_one_nsp(rar: Path, extraction_dir: Path, destination: Path):
    shutil.rmtree(extraction_dir, ignore_errors=True)
    extraction_dir.mkdir(parents=True)
    command = [sevenzip_executable(), "x", "-y", f"-o{extraction_dir}", str(rar)]
    subprocess.run(command, check=True)
    candidates = [x for x in extraction_dir.rglob("*")
                  if x.is_file() and x.suffix.lower() == ".nsp"]
    require(len(candidates) == 1,
            f"Archive must contain exactly one NSP, found {[x.name for x in candidates]}")
    found = candidates[0]
    with found.open("rb") as stream:
        require(stream.read(4) == b"PFS0", "Extracted file does not have NSP/PFS0 magic")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    shutil.move(str(found), str(destination))
    shutil.rmtree(extraction_dir, ignore_errors=True)
    print(f"[BioiOSMutant] NSP extracted: {destination.name} ({destination.stat().st_size:,} bytes)",
          flush=True)


def upload_checked(api, path: Path, drive_name: str) -> dict:
    md5, sha = file_hashes(path)
    uploaded = api.files().create(
        body={"name": drive_name, "parents": [GAME_FOLDER_ID]},
        media_body=MediaFileUpload(str(path), mimetype="application/octet-stream",
                                   chunksize=64 * 1024 * 1024, resumable=True),
        fields="id,name,size,md5Checksum", supportsAllDrives=True)
    response = None
    while response is None:
        status, response = uploaded.next_chunk(num_retries=6)
        if status:
            print(f"[BioiOSMutant] NSP -> Drive {drive_name}: {status.progress():.1%}",
                  flush=True)
    require(int(response["size"]) == path.stat().st_size and
            response.get("md5Checksum", "").lower() == md5,
            f"Drive upload of {drive_name} did not match local size/MD5")
    print(f"[BioiOSMutant] Upload verified: {drive_name}: SHA-256 {sha}", flush=True)
    return {"id": response["id"], "name": drive_name,
            "size": path.stat().st_size, "sha256": sha, "md5": md5}


def ingest(api, parent_folder_id: str, base_url: str, update_url: str,
           root: str = "/content/biomutant") -> dict:
    """Run after authenticating Colab Drive; never download both archives at once."""
    require(os.name == "posix" and Path("/content").exists(),
            "RAR download/extraction is designed for Linux Colab")
    from source_archive import FOLDER_MIME
    folders = [x for x in list_children(api, parent_folder_id)
               if x["id"] == GAME_FOLDER_ID and x.get("name", "").lower() == "biotant"
               and x.get("mimeType") == FOLDER_MIME]
    require(len(folders) == 1, "biotant Drive folder is missing or in the wrong parent")
    directory = Path(root)
    out = directory / "input-packages"
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for kind, url, name, filename in (
        ("base", base_url, "base.nsp", "000_base_biomutant.nsp"),
        ("update", update_url, "update.nsp", "100_update_biomutant.nsp"),
    ):
        remote = [f for f in list_children(api, GAME_FOLDER_ID)
                  if f.get("name", "").lower() == name]
        require(len(remote) <= 1, f"Duplicate {name} objects in the Drive folder")
        archive = directory / "archives" / f"{kind}.rar"
        destination = out / filename
        if remote and int(remote[0].get("size") or 0) > 0 and remote[0].get("md5Checksum"):
            results[kind] = {"id": remote[0]["id"], "name": name,
                             "size": int(remote[0]["size"]),
                             "md5": remote[0]["md5Checksum"],
                             "status": "already_on_drive"}
            print(f"[BioiOSMutant] Drive already has {name}: avoiding repeated download")
            archive.unlink(missing_ok=True)
            Path(str(archive) + '.downloaded').unlink(missing_ok=True)
            continue
        if remote:
            require(False, f"Existing {name} lacks valid size/MD5; resolve before upload")
        if not destination.is_file():
            download_rar(url, archive)
            extract_one_nsp(archive, directory / "archives" / f"{kind}-extracted",
                            destination)
        else:
            with destination.open("rb") as input_file:
                require(input_file.read(4) == b"PFS0", "Cached NSP has invalid PFS0 header")
        results[kind] = upload_checked(api, destination, name)
        # Delete the RAR only after the remote NSP size and MD5 are verified.
        archive.unlink(missing_ok=True)
        Path(str(archive) + '.downloaded').unlink(missing_ok=True)
        print(f"[BioiOSMutant] {kind} RAR removed after verified Drive upload", flush=True)
    require(len(results) == 2 and results["base"]["id"] != results["update"]["id"],
            "Both independent NSPs must be present in biotant")
    print("[BioiOSMutant] Source import complete. Linux build may now start.", flush=True)
    return results
