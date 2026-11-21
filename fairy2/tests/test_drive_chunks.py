#!/usr/bin/env python3
"""Offline regression tests for the Fairy2iOS shared Drive range downloader."""
from __future__ import annotations

import hashlib
import importlib
import io
import os
import re
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import drive_chunks as chunks


def _package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = []
    return module


class FakeDrive:
    def __init__(self, data: bytes, *, probe_ignored: bool = False,
                 corrupt: bool = False, one_retry: bool = False):
        self.data = data
        self.probe_ignored = probe_ignored
        self.corrupt = corrupt
        self.one_retry = one_retry
        self.failed_once = False
        self.lock = threading.Lock()
        self.sequential_calls = 0
        self.range_calls = 0

    def file(self):
        return {"id": "test-file", "name": "test.bin", "size": len(self.data),
                "sha256": hashlib.sha256(self.data).hexdigest(),
                "md5Checksum": hashlib.md5(self.data).hexdigest()}

    def api(self):
        outer = self
        class Api:
            _http = types.SimpleNamespace(credentials=object())
            def files(self):
                return self
            def get_media(self, fileId, supportsAllDrives):
                assert fileId == "test-file"
                return outer.data
        return Api()

    def installed_modules(self):
        outer = self

        class Response:
            def __init__(self, status_code, payload, content_range=""):
                self.status_code = status_code
                self.payload = payload
                self.headers = {"Content-Range": content_range}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code}")
            def iter_content(self, chunk_size):
                for i in range(0, len(self.payload), chunk_size):
                    yield self.payload[i:i + chunk_size]

        class Session:
            def __init__(self, credentials):
                assert credentials is not None
            def get(self, url, *, params, headers, stream, timeout):
                assert params["alt"] == "media"
                assert headers["Accept-Encoding"] == "identity"
                match = re.fullmatch(r"bytes=(\d+)-(\d+)", headers["Range"])
                assert match
                first, last = map(int, match.groups())
                with outer.lock:
                    outer.range_calls += 1
                    if (outer.one_retry and first == 8 and not outer.failed_once
                            and not (first == 0 and last == 0)):
                        outer.failed_once = True
                        raise OSError("simulated transient disconnect")
                if outer.probe_ignored:
                    return Response(200, outer.data)
                payload = outer.data[first:last + 1]
                if outer.corrupt and first == 8:
                    payload = b"?" * len(payload)
                return Response(206, payload, f"bytes {first}-{last}/{len(outer.data)}")

        class Status:
            def __init__(self, value):
                self.value = value
            def progress(self):
                return self.value

        class MediaIoBaseDownload:
            def __init__(self, stream, request, chunksize):
                self.stream, self.request, self.chunksize = stream, request, chunksize
                self._progress = 0
                outer.sequential_calls += 1
            def next_chunk(self):
                end = min(self._progress + self.chunksize, len(self.request))
                self.stream.write(self.request[self._progress:end])
                self._progress = end
                done = end >= len(self.request)
                return Status(end / len(self.request)), done

        names = {
            "googleapiclient": _package("googleapiclient"),
            "googleapiclient.http": types.ModuleType("googleapiclient.http"),
            "google": _package("google"),
            "google.auth": _package("google.auth"),
            "google.auth.transport": _package("google.auth.transport"),
            "google.auth.transport.requests": types.ModuleType("google.auth.transport.requests"),
        }
        names["googleapiclient.http"].MediaIoBaseDownload = MediaIoBaseDownload
        names["google.auth.transport.requests"].AuthorizedSession = Session
        return mock.patch.dict(sys.modules, names)


class ChunkedDriveTests(unittest.TestCase):
    def test_exact_ranges_cover_every_byte(self):
        with mock.patch.object(chunks, "RANGE_BYTES", 8):
            self.assertEqual(chunks._ranges(18), [(0, 7), (8, 15), (16, 17)])
            self.assertEqual(chunks._ranges(16), [(0, 7), (8, 15)])
            self.assertEqual(chunks._ranges(1), [(0, 0)])

    def _download(self, fake, *, second=False):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "test.bin"
            if second:
                output.write_bytes(b"x" * len(fake.data))
            with (fake.installed_modules(),
                  mock.patch.object(chunks, "RANGE_BYTES", 8),
                  mock.patch.object(chunks, "STREAM_BYTES", 3),
                  mock.patch.object(chunks, "FALLBACK_BYTES", 5),
                  mock.patch.object(chunks.time, "sleep", return_value=None)):
                record = chunks.download_drive_file(fake.api(), fake.file(), output)
                self.assertEqual(record["sha256"], hashlib.sha256(fake.data).hexdigest())
                self.assertEqual(output.read_bytes(), fake.data)
                self.assertFalse(output.with_suffix(".bin.part").exists())
                calls_before = fake.range_calls + fake.sequential_calls
                chunks.download_drive_file(fake.api(), fake.file(), output)
                self.assertEqual(fake.range_calls + fake.sequential_calls, calls_before)

    def test_parallel_64_mib_semantics_and_verified_cache(self):
        data = b"abcdefghij" * 3
        fake = FakeDrive(data)
        self._download(fake)
        self.assertGreater(fake.range_calls, 1)
        self.assertEqual(fake.sequential_calls, 0)

    def test_retry_only_failed_range(self):
        fake = FakeDrive(b"abcdefghij" * 3, one_retry=True)
        self._download(fake)
        self.assertTrue(fake.failed_once)
        self.assertEqual(fake.sequential_calls, 0)

    def test_ignore_range_falls_back_to_sequential_chunks(self):
        fake = FakeDrive(b"abcdefghij" * 3, probe_ignored=True)
        self._download(fake)
        self.assertEqual(fake.sequential_calls, 1)

    def test_corrupt_cached_file_is_replaced_and_verified(self):
        fake = FakeDrive(b"abcdefghij" * 3)
        self._download(fake, second=True)

    def test_download_integrity_failure_does_not_promote_file(self):
        fake = FakeDrive(b"abcdefghij" * 3, corrupt=True)
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "test.bin"
            with (fake.installed_modules(),
                  mock.patch.object(chunks, "RANGE_BYTES", 8),
                  mock.patch.object(chunks, "STREAM_BYTES", 3)):
                with self.assertRaises(RuntimeError):
                    chunks.download_drive_file(fake.api(), fake.file(), output)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
