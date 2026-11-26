#!/usr/bin/env python3
"""Colab-only NieR:Automata RAR ingestion: URL -> NSP -> verified Drive -> delete RAR.

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
        raise RuntimeError("[Nier2iOS RAR] " + message)


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
                print(f"[Nier2iOS] Verified cached RAR: {destination.name}, "
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
                    print("[Nier2iOS] Origin does not honor HTTP Range; "
                          "falling back to sequential 8 MiB streaming.", flush=True)
                    total = int(probe.headers.get("Content-Length", "0") or 0)
                else:
                    raise RuntimeError(f"Unexpected RAR probe HTTP {probe.status_code}")
            break
        except requests.RequestException as exc:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"RAR Range probe failed after {attempt} attempts: {exc}") from exc
            print(f"[Nier2iOS] RAR probe retry {attempt}/{MAX_ATTEMPTS}: "
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
            print(f"[Nier2iOS] {destination.name}: {len(entries)} × 64 MiB ranges, "
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
                            print(f"[Nier2iOS] {destination.name}: retry "
                                  f"{attempt}/{MAX_ATTEMPTS} for {start}-{end} in {delay}s "
                                  f"({type(exc).__name__})", flush=True)
                            time.sleep(delay)
                    raise RuntimeError("Unreachable RAR range retry limit")

                workers = min(MAX_WORKERS, len(pending))
                print(f"[Nier2iOS] {destination.name}: downloading with "
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
                            print(f"[Nier2iOS] {destination.name}: "
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
            print("[Nier2iOS] Source abandoned parallel ranges; "
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
                    prefix = b""
                    with part.open("wb") as output:
                        for block in response.iter_content(chunk_size=STREAM_BYTES):
                            if not block:
                                continue
                            # HTTP iter_content may yield fewer bytes than its
                            # chunk_size. Assemble the 8-byte RAR signature
                            # across chunks instead of assuming block[0] is
                            # at least four bytes long.
                            if len(prefix) < 8:
                                prefix += block[:8 - len(prefix)]
                                if len(prefix) == 8:
                                    require(any(prefix.startswith(magic) for magic in RAR_MAGIC),
                                            "RAR link returned HTML or invalid content instead of a RAR")
                            output.write(block)
                            transferred += len(block)
                            if length and transferred % (64 * 1024 * 1024) < len(block):
                                print(f"[Nier2iOS] {destination.name}: "
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
                print(f"[Nier2iOS] Sequential retry {attempt}/{MAX_ATTEMPTS}: "
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
    print(f"[Nier2iOS] Verified RAR download {destination.name}: "
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


def _rar_extraction_command(name: str, executable: str, rar: Path,
                            extraction_dir: Path) -> list[str]:
    if name == "unrar":
        # -p- disables interactive password prompts in unattended Colab sessions.
        return [executable, "x", "-y", "-o+", "-p-", str(rar),
                str(extraction_dir) + "/"]
    if name == "unar":
        return [executable, "-quiet", "-force-overwrite",
                "-output-directory", str(extraction_dir), str(rar)]
    return [executable, "x", "-y", f"-o{extraction_dir}", str(rar)]


def _install_rar_fallback(name: str) -> str | None:
    """Try supported Linux RAR readers only after a preinstalled reader fails."""
    package = {"7zz": "7zip", "unrar": "unrar", "unar": "unar"}[name]
    existing = shutil.which(name)
    if existing:
        return existing
    print(f"[Nier2iOS] Checking Linux RAR fallback: {package}", flush=True)
    try:
        result = subprocess.run(
            ["apt-get", "install", "-y", "-qq", package],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", check=False, timeout=240)
        if result.returncode:
            print(f"[Nier2iOS] Package {package} unavailable "
                  f"(apt exit {result.returncode}); trying next reader.", flush=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[Nier2iOS] Could not install {package}: {type(exc).__name__}", flush=True)
    return shutil.which(name)


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
            print(f"[Nier2iOS] NSP -> Drive {drive_name}: {status.progress():.1%}",
                  flush=True)
    require(int(response["size"]) == path.stat().st_size and
            response.get("md5Checksum", "").lower() == md5,
            f"Drive upload of {drive_name} did not match local size/MD5")
    print(f"[Nier2iOS] Upload verified: {drive_name}: SHA-256 {sha}", flush=True)
    return {"id": response["id"], "name": drive_name,
            "size": path.stat().st_size, "sha256": sha, "md5": md5}


def _remove_verified_rar(archive):
    archive.unlink(missing_ok=True)
    for ext in (".downloaded.json", ".part", ".part.json"):
        Path(str(archive) + ext).unlink(missing_ok=True)

def _get_remote(children, filename):
    items = [x for x in children if x.get("name", "").casefold() == filename.casefold()]
    require(len(items) <= 1, f"Duplicate Drive NSP: {filename}")
    if not items:
        return None
    item = items[0]
    require(int(item.get("size") or 0) > 4 and bool(item.get("md5Checksum")),
            f"Drive NSP has invalid remote size/MD5: {filename}")
    return item


def extract_packages(first, directory, suffix, expected=None):
    directory = Path(directory)
    initial = sevenzip_executable()
    failures = []
    for kind in ("initial", "7zz", "unrar", "unar"):
        exe = initial if kind == "initial" else _install_rar_fallback(kind)
        if not exe: continue
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        command = _rar_extraction_command(Path(exe).name, exe, Path(first), directory)
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        if result.returncode:
            failures.append(result.stdout[-4000:])
            continue
        files = sorted(p for p in directory.rglob("*") if p.is_file() and not p.is_symlink()
                       and p.suffix.lower() == suffix and p.resolve().is_relative_to(directory.resolve()))
        require(files and (expected is None or len(files) == expected), "Unexpected extracted package count")
        for path in files:
            with path.open("rb") as inp:
                if suffix == ".xci": inp.seek(0x100)
                require(inp.read(4) == (b"HEAD" if suffix == ".xci" else b"PFS0"), "Invalid package header")
        return files
    raise RuntimeError("RAR extraction failed; source retained:\n" + "\n".join(failures))

def ingest(api, parent_folder_id, base_urls, update_url, dlc_url, translation_url, root="/content/nier"):
    import zipfile
    root = Path(root) / "ingest"
    root.mkdir(parents=True, exist_ok=True)
    require(any(x["id"] == GAME_FOLDER_ID and x["name"] == "nier" for x in list_children(api,parent_folder_id)), "Wrong Drive parent")
    def remote(name):
        return _get_remote(list_children(api, GAME_FOLDER_ID), name)
    def store(path, name):
        existing = remote(name)
        if existing:
            md5, sha = file_hashes(path)
            require(int(existing["size"]) == path.stat().st_size and existing["md5Checksum"].lower() == md5, "Existing Drive file differs: " + name)
            return {"id":existing["id"], "sha256":sha, "size":path.stat().st_size}
        return upload_checked(api, path, name)
    require(len(base_urls) == 3, "Expected exactly three base RAR parts")
    for group, urls, suffix, expected in (("base", base_urls, ".xci", 1), ("update",[update_url],".nsp",1), ("dlc",[dlc_url],".nsp",None)):
        target = "base.xci" if group == "base" else "update.nsp"
        dlc_manifest = remote("dlc-inventory.json") if group == "dlc" else None
        if group != "dlc" and remote(target): continue
        if dlc_manifest:
            import io, json
            from googleapiclient.http import MediaIoBaseDownload
            buf=io.BytesIO(); download=MediaIoBaseDownload(buf,api.files().get_media(fileId=dlc_manifest["id"]))
            done=False
            while not done: _,done=download.next_chunk(num_retries=5)
            inventory=json.loads(buf.getvalue())
            for name in inventory:
                require(remote(name), "Incomplete DLC cache")
            continue
        archives=[]
        for i,url in enumerate(urls,1):
            archive=root/(f"base.part{i}.rar" if group=="base" else f"{group}.rar")
            require(bool(url), "Missing source URL for " + group)
            download_rar(url,archive); archives.append(archive)
        extracted=extract_packages(archives[0], root/(group+"-extract"), suffix, expected)
        names=[]
        for i,path in enumerate(extracted,1):
            name=f"dlc-{i:02d}.nsp" if group=="dlc" else target
            store(path,name); names.append(name)
        if group=="dlc":
            import json
            inventory=root/"dlc-inventory.json"
            inventory.write_text(json.dumps(names))
            store(inventory,inventory.name)
        for archive in archives: _remove_verified_rar(archive)
        shutil.rmtree(root/(group+"-extract"))
    if not remote("translation.zip"):
        require(translation_url.startswith("https://"), "Translation URL missing")
        path=root/"translation.zip"
        temp=path.with_suffix(".part")
        with requests.get(translation_url,stream=True,timeout=(20,180)) as response:
            response.raise_for_status()
            with temp.open("wb") as out:
                size=0
                for chunk in response.iter_content(8*1024*1024):
                    if chunk:
                        out.write(chunk); size+=len(chunk)
                        print(f"PT-BR: {size/2**20:.1f} MiB",flush=True)
        temp.replace(path)
        with zipfile.ZipFile(path) as z:
            require(z.testzip() is None, "Invalid translation ZIP CRC")
        store(path,"translation.zip")
        path.unlink()
    print("Nier2iOS source ingestion complete; RARs removed only after verified uploads.",flush=True)
