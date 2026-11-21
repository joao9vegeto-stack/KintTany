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


RANGE_BYTES = 64 * 1024 * 1024
STREAM_BYTES = 8 * 1024 * 1024
MAX_WORKERS = 6
MAX_ATTEMPTS = 5


class OriginRangeUnsupported(RuntimeError):
    """A source link did not consistently honor byte-range requests."""


def _source_key(url: str) -> str:
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    require(parsed.scheme == "https" and bool(parsed.netloc),
            "RAR source must be an absolute HTTPS URL")
    # Temporary download_token query strings may change between Colab runs.
    return parsed.netloc.casefold() + parsed.path


def _save_json_atomic(path: Path, data: dict) -> None:
    import json
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _range_hash(path: Path, offset: int, length: int) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        while length:
            block = stream.read(min(STREAM_BYTES, length))
            if not block:
                return ""
            sha.update(block)
            length -= len(block)
    return sha.hexdigest()


def _pwrite_all(fd: int, data: bytes, offset: int) -> None:
    view = memoryview(data)
    while view:
        count = os.pwrite(fd, view, offset)
        require(count > 0, "Incomplete positional write during RAR transfer")
        view = view[count:]
        offset += count


def _ranges(total: int) -> list[tuple[int, int]]:
    return [(start, min(start + RANGE_BYTES, total) - 1)
            for start in range(0, total, RANGE_BYTES)]


def download_rar(url: str, destination: Path) -> dict:
    """Six concurrent 64 MiB HTTP ranges with verified resumable chunks.

    Each successfully completed chunk is SHA-256 indexed. On restart, chunks
    are read back and re-hashed before reuse; sparse holes are not trusted.
    Source links with no Range support use an explicitly reported 8 MiB
    sequential streaming fallback. RAR integrity is also checked by 7-Zip
    during extraction, before the archives are deleted.
    """
    import concurrent.futures as futures
    import json
    import re
    import threading
    from http.client import IncompleteRead

    source = _source_key(url)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    complete = Path(str(destination) + ".downloaded.json")
    part = Path(str(destination) + ".part")
    ledger = Path(str(destination) + ".part.json")
    marker = None
    if destination.is_file() and complete.is_file() and not destination.is_symlink():
        try:
            marker = json.loads(complete.read_text())
            _, sha = file_hashes(destination)
            with destination.open("rb") as stream:
                magic = stream.read(8)
            if (marker.get("source") == source
                    and marker.get("size") == destination.stat().st_size
                    and marker.get("sha256") == sha
                    and any(magic.startswith(m) for m in RAR_MAGIC)):
                print(f"[BioiOSMutant] Verified cached RAR: {destination.name}, "
                      f"SHA-256 {sha}", flush=True)
                return marker
        except (ValueError, OSError, TypeError):
            pass
    complete.unlink(missing_ok=True)

    base_headers = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"}
    total = None
    etag = ""
    last_modified = ""
    range_supported = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with requests.get(url, headers={**base_headers, "Range": "bytes=0-0"},
                              stream=True, timeout=(30, 180), allow_redirects=True) as probe:
                if probe.status_code in (401, 403, 404, 410):
                    raise RuntimeError(f"Source HTTP {probe.status_code}; RAR link may have expired")
                probe.raise_for_status()
                if probe.status_code == 206:
                    match = re.fullmatch(
                        r"bytes 0-0/([1-9][0-9]*)",
                        probe.headers.get("Content-Range", "").strip())
                    require(match is not None, "Invalid RAR Range probe Content-Range")
                    total = int(match.group(1))
                    first_byte = next(probe.iter_content(chunk_size=1), b"")
                    require(first_byte == b"R",
                            "RAR link returned an unexpected first byte (HTML/expired URL?)")
                    if probe.headers.get("Content-Encoding", "identity").lower() != "identity":
                        raise RuntimeError("RAR HTTP Range probe uses an unsupported content encoding")
                    etag = probe.headers.get("ETag", "")
                    last_modified = probe.headers.get("Last-Modified", "")
                    range_supported = True
                elif probe.status_code == 200:
                    print("[BioiOSMutant] Origin does not honor HTTP Range; "
                          "falling back to sequential 8 MiB streaming.", flush=True)
                    total = int(probe.headers.get("Content-Length", "0") or 0)
                else:
                    raise RuntimeError(f"Unexpected RAR probe HTTP {probe.status_code}")
            break
        except requests.RequestException as exc:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"RAR Range probe failed after {attempt} attempts: {exc}") from exc
            print(f"[BioiOSMutant] RAR probe retry {attempt}/{MAX_ATTEMPTS}: "
                  f"{type(exc).__name__}", flush=True)
            time.sleep(min(2 ** attempt, 16))

    started = time.monotonic()
    completed_chunks = {}
    if range_supported:
        entries = _ranges(total)
        metadata = {"format": 1, "source": source, "size": total,
                    "etag": etag, "last_modified": last_modified, "chunks": {}}
        old = None
        if ledger.is_file() and part.is_file() and not part.is_symlink():
            try:
                old = json.loads(ledger.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        if (old and all(old.get(k) == metadata[k] for k in
                        ("format", "source", "size", "etag", "last_modified"))
                and part.stat().st_size == total):
            for start, end in entries:
                key = str(start)
                expected = old.get("chunks", {}).get(key)
                if expected and _range_hash(part, start, end - start + 1) == expected:
                    completed_chunks[key] = expected
        else:
            part.unlink(missing_ok=True)
            ledger.unlink(missing_ok=True)
        metadata["chunks"] = completed_chunks
        fd = os.open(part, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            os.ftruncate(fd, total)
            _save_json_atomic(ledger, metadata)
            pending = [(start, end) for start, end in entries
                       if str(start) not in completed_chunks]
            saved = sum(end - start + 1 for start, end in entries
                        if str(start) in completed_chunks)
            print(f"[BioiOSMutant] {destination.name}: {len(entries)} × 64 MiB ranges, "
                  f"{len(completed_chunks)} SHA-256-verified chunks reused; "
                  f"{len(pending)} pending.", flush=True)
            if pending:
                local = threading.local()
                stop = threading.Event()

                def session():
                    if not hasattr(local, "session"):
                        local.session = requests.Session()
                    return local.session

                def fetch_range(start: int, end: int):
                    size = end - start + 1
                    for attempt in range(1, MAX_ATTEMPTS + 1):
                        if stop.is_set():
                            raise RuntimeError("Parallel transfer cancelled")
                        try:
                            with session().get(
                                url, headers={**base_headers,
                                              "Range": f"bytes={start}-{end}"},
                                stream=True, timeout=(30, 180),
                                allow_redirects=True) as response:
                                if response.status_code == 200:
                                    stop.set()
                                    raise OriginRangeUnsupported(
                                        "RAR host ignored an in-progress Range request")
                                if response.status_code in (401, 403, 404, 410):
                                    raise RuntimeError(
                                        f"RAR source HTTP {response.status_code}: expired or inaccessible")
                                response.raise_for_status()
                                if response.status_code != 206:
                                    raise RuntimeError(
                                        f"RAR Range {start}-{end}: HTTP {response.status_code}")
                                value = response.headers.get("Content-Range", "").strip()
                                require(value == f"bytes {start}-{end}/{total}",
                                        f"RAR host returned mismatched Content-Range {value!r}")
                                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                                    stop.set()
                                    raise OriginRangeUnsupported("Encoded source ranges are not byte-exact")
                                if etag and response.headers.get("ETag", etag) != etag:
                                    raise RuntimeError("RAR changed ETag while downloading")
                                if last_modified and response.headers.get("Last-Modified", last_modified) != last_modified:
                                    raise RuntimeError("RAR changed Last-Modified during download")
                                sha = hashlib.sha256()
                                written = 0
                                for block in response.iter_content(chunk_size=STREAM_BYTES):
                                    if not block:
                                        continue
                                    if stop.is_set():
                                        raise OriginRangeUnsupported("Range transfer cancelled")
                                    require(written + len(block) <= size,
                                            "RAR host sent too many bytes for a range")
                                    _pwrite_all(fd, block, start + written)
                                    sha.update(block)
                                    written += len(block)
                                if written != size:
                                    raise IncompleteRead(
                                        f"RAR Range {start}-{end} incomplete: {written}/{size}")
                                return start, end, sha.hexdigest()
                        except OriginRangeUnsupported:
                            raise
                        except Exception as exc:
                            if attempt == MAX_ATTEMPTS:
                                raise RuntimeError(
                                    f"RAR Range {start}-{end} failed after "
                                    f"{MAX_ATTEMPTS} attempts: {exc}") from exc
                            delay = min(2 ** (attempt - 1), 16)
                            print(f"[BioiOSMutant] {destination.name}: retry "
                                  f"{attempt}/{MAX_ATTEMPTS} for {start}-{end} in {delay}s "
                                  f"({type(exc).__name__})", flush=True)
                            time.sleep(delay)
                    raise RuntimeError("Unreachable RAR range retry limit")

                workers = min(MAX_WORKERS, len(pending))
                print(f"[BioiOSMutant] {destination.name}: downloading with "
                      f"{workers} workers × 64 MiB HTTP ranges.", flush=True)
                try:
                    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
                        jobs = {pool.submit(fetch_range, a, b): (a, b) for a, b in pending}
                        for future in futures.as_completed(jobs):
                            start, end, digest = future.result()
                            # Commit a range only after the data is flushed to disk.
                            os.fsync(fd)
                            metadata["chunks"][str(start)] = digest
                            _save_json_atomic(ledger, metadata)
                            saved += end - start + 1
                            elapsed = max(time.monotonic() - started, 0.001)
                            print(f"[BioiOSMutant] {destination.name}: "
                                  f"{saved / total:.1%} "
                                  f"({saved / 2**30:.2f}/{total / 2**30:.2f} GiB), "
                                  f"{saved / elapsed / 2**20:.1f} MiB/s.", flush=True)
                except OriginRangeUnsupported:
                    stop.set()
                    range_supported = False
                except BaseException:
                    stop.set()
                    raise
            if range_supported:
                require(len(metadata["chunks"]) == len(entries),
                        "Cannot finalize incomplete RAR range ledger")
        finally:
            os.close(fd)
        if not range_supported:
            part.unlink(missing_ok=True)
            ledger.unlink(missing_ok=True)
            print("[BioiOSMutant] Source abandoned parallel ranges; "
                  "restarting with safe sequential streaming.", flush=True)

    if not range_supported:
        ledger.unlink(missing_ok=True)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                with requests.get(url, headers=base_headers, stream=True,
                                  timeout=(30, 180), allow_redirects=True) as response:
                    if response.status_code in (401, 403, 404, 410):
                        raise RuntimeError(
                            f"Source HTTP {response.status_code}; RAR URL may have expired")
                    response.raise_for_status()
                    require(response.status_code == 200, "Sequential RAR response must be HTTP 200")
                    length = int(response.headers.get("Content-Length", "0") or 0)
                    require(total in (None, 0) or length in (0, total),
                            "RAR source changed size after Range probe")
                    transferred = 0
                    with part.open("wb") as output:
                        for block in response.iter_content(chunk_size=STREAM_BYTES):
                            if not block:
                                continue
                            if transferred == 0:
                                require(block.startswith(b"Rar!"),
                                        "RAR link returned HTML or invalid content instead of a RAR")
                            output.write(block)
                            transferred += len(block)
                            if length and transferred % (64 * 1024 * 1024) < len(block):
                                print(f"[BioiOSMutant] {destination.name}: "
                                      f"{transferred / length:.1%} in sequential 8 MiB blocks",
                                      flush=True)
                        output.flush()
                        os.fsync(output.fileno())
                    require(transferred > 8 and (not length or transferred == length)
                            and (not total or transferred == total),
                            "Sequential RAR download truncated or inconsistent")
                break
            except (requests.RequestException, OSError, RuntimeError) as exc:
                if "Source HTTP" in str(exc) or "RAR link returned HTML" in str(exc):
                    raise
                if attempt == MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"Sequential RAR download failed after {attempt} attempts: "
                        f"{type(exc).__name__}") from exc
                print(f"[BioiOSMutant] Sequential retry {attempt}/{MAX_ATTEMPTS}: "
                      f"{type(exc).__name__}", flush=True)
                time.sleep(min(2 ** attempt, 16))

    require(part.is_file() and part.stat().st_size >= 8, "RAR transfer incomplete")
    with part.open("rb") as inp:
        header = inp.read(8)
    require(any(header.startswith(m) for m in RAR_MAGIC),
            "RAR link delivered HTML/invalid data; refresh the signed download URL")
    # End-to-end digest of the entire assembled archive, not only its chunks.
    _, sha256 = file_hashes(part)
    size = part.stat().st_size
    part.replace(destination)
    ledger.unlink(missing_ok=True)
    marker = {"source": source, "size": size, "sha256": sha256,
              "etag": etag, "last_modified": last_modified,
              "chunk_bytes": RANGE_BYTES,
              "mode": "parallel_ranges" if range_supported else "sequential_fallback"}
    _save_json_atomic(complete, marker)
    elapsed = max(time.monotonic() - started, 0.001)
    print(f"[BioiOSMutant] Verified RAR download {destination.name}: "
          f"{size:,} bytes, SHA-256 {sha256}, "
          f"{size / elapsed / 2**20:.1f} MiB/s "
          f"({marker['mode']}).", flush=True)
    return marker


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
            Path(str(archive) + ".downloaded.json").unlink(missing_ok=True)
            Path(str(archive) + ".part").unlink(missing_ok=True)
            Path(str(archive) + ".part.json").unlink(missing_ok=True)
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
        Path(str(archive) + ".downloaded.json").unlink(missing_ok=True)
        Path(str(archive) + ".part").unlink(missing_ok=True)
        Path(str(archive) + ".part.json").unlink(missing_ok=True)
        print(f"[BioiOSMutant] {kind} RAR removed after verified Drive upload", flush=True)
    require(len(results) == 2 and results["base"]["id"] != results["update"]["id"],
            "Both independent NSPs must be present in biotant")
    print("[BioiOSMutant] Source import complete. Linux build may now start.", flush=True)
    return results
