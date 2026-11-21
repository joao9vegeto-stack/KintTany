#!/usr/bin/env python3
"""Verified 64-MiB HTTP Range transfers for the BioiOSMutant Colab and Actions stages.

Adapted from KaKaRoTiOS/scripts/prepare_kakarot_actions.py.
A response is never trusted solely because it has HTTP 200 or a matching byte count.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import os
import re
import threading
import time
from http.client import IncompleteRead
from pathlib import Path
from urllib.parse import quote

RANGE_BYTES = 64 * 1024 * 1024
STREAM_BYTES = 8 * 1024 * 1024
FALLBACK_BYTES = 32 * 1024 * 1024
MAX_WORKERS = 6


class DriveRangeNotSupported(RuntimeError):
    """The Drive endpoint stopped returning full, consistent HTTP 206 ranges."""


def _hashes(path: Path) -> tuple[str, str]:
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open("rb") as inp:
        for data in iter(lambda: inp.read(STREAM_BYTES), b""):
            sha.update(data)
            md5.update(data)
    return sha.hexdigest(), md5.hexdigest()


def _ident(item: dict) -> tuple[int, str, str]:
    size = int(item.get("size") or 0)
    sha = str(item.get("sha256") or "").lower()
    md5 = str(item.get("md5Checksum") or item.get("md5") or "").lower()
    if size <= 0 or not item.get("id"):
        raise ValueError("Missing Drive file ID or size for a verified transfer")
    if sha and not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError(f"Invalid Drive SHA-256 for {item.get('name')}")
    if md5 and not re.fullmatch(r"[0-9a-f]{32}", md5):
        raise ValueError(f"Invalid Drive MD5 for {item.get('name')}")
    if not sha and not md5:
        raise ValueError(f"Drive file {item.get('name')}: no SHA-256 or MD5 checksum supplied")
    return size, sha, md5


def _pwrite_all(fd: int, data: bytes, offset: int) -> None:
    view = memoryview(data)
    while view:
        count = os.pwrite(fd, view, offset)
        if count <= 0:
            raise OSError("short positional write while transferring Drive file")
        offset += count
        view = view[count:]


def _ranges(size: int) -> list[tuple[int, int]]:
    return [(start, min(start + RANGE_BYTES, size) - 1)
            for start in range(0, size, RANGE_BYTES)]


def _check_file(path: Path, size: int, sha: str, md5: str) -> tuple[bool, str]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != size:
        return False, ""
    real_sha, real_md5 = _hashes(path)
    return (not sha or real_sha == sha) and (not md5 or real_md5 == md5), real_sha


def download_drive_file(api, item: dict, destination: Path, *, credentials=None,
                        parallel_workers: int = MAX_WORKERS) -> dict:
    """Six independent 64 MiB range workers; 32 MiB chunked, retryable fallback.

    Files are promoted atomically only after size and SHA-256/MD5 verification.
    An already-complete, verified destination is reused without another download.
    Failed ranges retry in place. A stale partial file is restarted, never
    mistaken for a complete sparse file.
    """
    from googleapiclient.http import MediaIoBaseDownload

    expected_size, expected_sha, expected_md5 = _ident(item)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    name = str(item.get("name") or item["id"])
    valid, reused_sha = _check_file(destination, expected_size, expected_sha, expected_md5)
    if valid:
        print(f"[BioiOSMutant] Drive cache verified: {name}, {expected_size:,} bytes, SHA-256 {reused_sha}", flush=True)
        return {"id": item["id"], "name": name, "size": expected_size, "sha256": reused_sha}

    # The API uses google_auth_httplib2.AuthorizedHttp for both Colab OAuth
    # and Actions' service-account Credentials.
    if credentials is None:
        credentials = getattr(getattr(api, "_http", None), "credentials", None)
    use_ranges = expected_size >= RANGE_BYTES and credentials is not None
    if expected_size >= RANGE_BYTES and credentials is None:
        print("[BioiOSMutant] Authenticated Range session unavailable; "
              "using verified 32 MiB chunked API downloader.", flush=True)

    start_time = time.monotonic()
    part = destination.with_suffix(destination.suffix + ".part")
    part.unlink(missing_ok=True)
    range_supported = False

    if use_ranges:
        from google.auth.transport.requests import AuthorizedSession
        local = threading.local()
        url = f"https://www.googleapis.com/drive/v3/files/{quote(str(item['id']), safe='')}"
        params = {"alt": "media", "supportsAllDrives": "true"}

        def current_session():
            session = getattr(local, "session", None)
            if session is None:
                session = AuthorizedSession(credentials)
                local.session = session
            return session

        with current_session().get(
            url, params=params,
            headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"},
            stream=True, timeout=(30, 180),
        ) as probe:
            if probe.status_code == 206:
                wanted = f"bytes 0-0/{expected_size}"
                actual = probe.headers.get("Content-Range", "").strip()
                if actual != wanted or len(next(probe.iter_content(chunk_size=1), b"")) != 1:
                    raise RuntimeError(f"Drive returned an invalid Range probe for {name}: {actual!r}")
                range_supported = True
            elif probe.status_code == 200:
                print(f"[BioiOSMutant] {name}: server ignored Range probe, using sequential chunks.", flush=True)
            else:
                probe.raise_for_status()
                raise RuntimeError(f"Unexpected HTTP {probe.status_code} during Drive Range probe")

        if range_supported:
            chunks = _ranges(expected_size)
            workers = min(MAX_WORKERS, max(1, int(parallel_workers)), len(chunks))
            fd = os.open(part, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                os.ftruncate(fd, expected_size)

                def fetch_range(start: int, end: int) -> int:
                    length = end - start + 1
                    for attempt in range(1, 6):
                        try:
                            with current_session().get(
                                url, params=params,
                                headers={
                                    "Range": f"bytes={start}-{end}",
                                    "Accept-Encoding": "identity",
                                }, stream=True, timeout=(30, 180),
                            ) as response:
                                if response.status_code == 200:
                                    raise DriveRangeNotSupported(
                                        "Drive stopped honoring Range headers mid-transfer")
                                if response.status_code != 206:
                                    response.raise_for_status()
                                    raise RuntimeError(f"Range {start}-{end}: HTTP {response.status_code}")
                                actual = response.headers.get("Content-Range", "").strip()
                                wanted = f"bytes {start}-{end}/{expected_size}"
                                if actual != wanted:
                                    raise RuntimeError(
                                        f"Range {start}-{end}: invalid Content-Range {actual!r}")
                                written = 0
                                for block in response.iter_content(chunk_size=STREAM_BYTES):
                                    if not block:
                                        continue
                                    if written + len(block) > length:
                                        raise RuntimeError(f"Range {start}-{end}: overlength data")
                                    _pwrite_all(fd, block, start + written)
                                    written += len(block)
                                if written != length:
                                    raise IncompleteRead(
                                        f"Range {start}-{end}: {written}/{length} bytes received")
                                return written
                        except DriveRangeNotSupported:
                            raise
                        except Exception as exc:
                            if attempt >= 5:
                                raise RuntimeError(f"Range {start}-{end} failed after 5 tries: {exc}") from exc
                            delay = min(2 ** (attempt - 1), 16)
                            print(f"[BioiOSMutant] {name}: retry {attempt}/5 of "
                                  f"range {start}-{end} in {delay}s ({type(exc).__name__})", flush=True)
                            time.sleep(delay)
                    raise RuntimeError("unreachable exhausted Range retries")

                transferred, report_stride = 0, max(256 * 1024 * 1024, int(expected_size * 0.02))
                report_next = report_stride
                try:
                    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
                        tasks = [pool.submit(fetch_range, first, last) for first, last in chunks]
                        for future in cf.as_completed(tasks):
                            transferred += future.result()
                            if transferred >= report_next or transferred == expected_size:
                                elapsed = max(time.monotonic() - start_time, 0.001)
                                print(f"[BioiOSMutant] Drive {name}: {transferred / expected_size:.1%} "
                                      f"({transferred / 2**30:.2f}/{expected_size / 2**30:.2f} GiB), "
                                      f"{transferred / elapsed / 2**20:.1f} MiB/s, "
                                      f"{workers} workers × 64 MiB.", flush=True)
                                report_next += report_stride
                except DriveRangeNotSupported:
                    range_supported = False
                if range_supported:
                    os.fsync(fd)
            finally:
                os.close(fd)

    if not range_supported:
        part.unlink(missing_ok=True)
        request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
        with part.open("wb") as output:
            reader = MediaIoBaseDownload(output, request, chunksize=FALLBACK_BYTES)
            done, errors = False, 0
            while not done:
                try:
                    status, done = reader.next_chunk()
                    errors = 0
                except (IncompleteRead, TimeoutError, ConnectionError, OSError) as exc:
                    errors += 1
                    if errors > 10:
                        raise RuntimeError(f"{name}: interrupted at {reader._progress}, "
                                           f"more than 10 retries: {exc}") from exc
                    delay = min(2 ** min(errors, 5), 30)
                    print(f"[BioiOSMutant] {name}: sequential chunk retry {errors}/10 "
                          f"at {reader._progress} in {delay}s", flush=True)
                    time.sleep(delay)
                    continue
                if status:
                    print(f"[BioiOSMutant] Drive {name}: {status.progress() * 100:.1f}% "
                          f"(32 MiB chunks)", flush=True)

    valid, actual_sha = _check_file(part, expected_size, expected_sha, expected_md5)
    if not valid:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"{name}: downloaded file did not match Drive size/SHA-256/MD5 metadata")
    part.replace(destination)
    elapsed = max(time.monotonic() - start_time, 0.001)
    print(f"[BioiOSMutant] Drive download VERIFIED: {name} {expected_size:,} bytes; "
          f"SHA-256 {actual_sha}, {expected_size / elapsed / 2**20:.1f} MiB/s", flush=True)
    return {"id": item["id"], "name": name, "size": expected_size, "sha256": actual_sha}
