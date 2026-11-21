#!/usr/bin/env python3
"""Offline regressions for six-worker RAR ranged download, resume and fallback."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "colab"))
sys.path.insert(0, str(ROOT))
# archive_ingest imports Google API and Drive source loader; stub dependencies
# only when they are absent in the Linux preflight interpreter.
try:
    from googleapiclient.http import MediaFileUpload  # noqa: F401
except ImportError:
    import types
    googleapiclient = types.ModuleType("googleapiclient")
    http = types.ModuleType("googleapiclient.http")
    http.MediaFileUpload = object
    googleapiclient.http = http
    sys.modules["googleapiclient"] = googleapiclient
    sys.modules["googleapiclient.http"] = http

import archive_ingest as rar

RAR = b"Rar!\x1a\x07\x00" + bytes(range(1, 78))


class Response:
    def __init__(self, status, content, headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index:index + chunk_size]


class FakeRARServer:
    def __init__(self, data: bytes, *, ignore_ranges=False, bad_range=False,
                 fail_range_start=None, status=None):
        self.data = data
        self.ignore_ranges = ignore_ranges
        self.bad_range = bad_range
        self.fail_range_start = fail_range_start
        self.status = status
        self.calls = []
        self.lock = threading.Lock()

    def response(self, url, *, headers, stream, timeout, allow_redirects):
        if self.status is not None:
            return Response(self.status, b"", {})
        requested = headers.get("Range")
        with self.lock:
            self.calls.append(requested)
        if not requested or self.ignore_ranges:
            return Response(200, self.data,
                            {"Content-Length": str(len(self.data))})
        matched = re.fullmatch(r"bytes=(\d+)-(\d+)", requested)
        assert matched, f"Invalid Range header: {requested}"
        start, end = (int(x) for x in matched.groups())
        if self.fail_range_start == start and requested != "bytes=0-0":
            raise ConnectionError("Fake intermittent source failure")
        content_range = f"bytes {start}-{end}/{len(self.data)}"
        if self.bad_range and requested != "bytes=0-0":
            content_range = f"bytes {start}-{end}/{len(self.data) + 1}"
        return Response(206, self.data[start:end+1],
                        {"Content-Range": content_range,
                         "ETag": '"test-blob"',
                         "Last-Modified": "Fri, 20 Nov 2026 01:00:00 GMT"})

    def session_factory(self):
        host = self

        class Session:
            def get(self, *a, **kw):
                return host.response(*a, **kw)

        return Session()


class RARRangeTests(unittest.TestCase):
    URL = "https://example.com/biomutant/base.rar?download_token=secret"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / "base.rar"

    def run_source(self, host):
        with mock.patch.object(rar, "RANGE_BYTES", 8), \
                mock.patch.object(rar, "STREAM_BYTES", 3), \
                mock.patch.object(rar, "MAX_WORKERS", 6), \
                mock.patch.object(rar.time, "sleep", return_value=None), \
                mock.patch.object(rar.requests, "get", side_effect=host.response), \
                mock.patch.object(rar.requests, "Session",
                                  side_effect=host.session_factory):
            return rar.download_rar(self.URL, self.destination)

    def test_six_workers_parallel_chunks_and_cache_hash(self):
        host = FakeRARServer(RAR)
        result = self.run_source(host)
        self.assertEqual(result["mode"], "parallel_ranges")
        self.assertEqual(self.destination.read_bytes(), RAR)
        self.assertEqual(result["sha256"], hashlib.sha256(RAR).hexdigest())
        self.assertIn("bytes=0-0", host.calls)
        self.assertIn("bytes=0-7", host.calls)
        self.assertIn("bytes=80-84", host.calls)
        count = len(host.calls)
        self.assertEqual(self.run_source(host), result)
        self.assertEqual(len(host.calls), count)
        self.assertNotIn("secret", str(result))

    def _seed_chunk(self, *, corrupt=False):
        host = FakeRARServer(RAR)
        source = rar._source_key(self.URL)
        partial = Path(str(self.destination) + ".part")
        partial.write_bytes(b"\0" * len(RAR))
        with partial.open("r+b") as stream:
            stream.seek(0)
            stream.write((b"X" if corrupt else RAR[:1]) + RAR[1:8])
        ledger = {
            "format": 1, "source": source, "size": len(RAR),
            "etag": '"test-blob"',
            "last_modified": "Fri, 20 Nov 2026 01:00:00 GMT",
            "chunks": {"0": hashlib.sha256(RAR[:8]).hexdigest()},
        }
        Path(str(self.destination) + ".part.json").write_text(json.dumps(ledger))
        return host

    def test_resume_rehashes_and_skips_good_chunks(self):
        host = self._seed_chunk()
        self.run_source(host)
        self.assertEqual(self.destination.read_bytes(), RAR)
        self.assertNotIn("bytes=0-7", host.calls)

    def test_corrupt_partial_chunk_is_redownloaded(self):
        host = self._seed_chunk(corrupt=True)
        self.run_source(host)
        self.assertEqual(self.destination.read_bytes(), RAR)
        self.assertIn("bytes=0-7", host.calls)

    def test_server_ignores_ranges_falls_back_to_eight_mib_streaming(self):
        host = FakeRARServer(RAR, ignore_ranges=True)
        result = self.run_source(host)
        self.assertEqual(result["mode"], "sequential_fallback")
        self.assertEqual(self.destination.read_bytes(), RAR)
        self.assertEqual(host.calls, ["bytes=0-0", None])

    def test_mismatched_content_range_never_promotes_rar(self):
        host = FakeRARServer(RAR, bad_range=True)
        with self.assertRaises(RuntimeError):
            self.run_source(host)
        self.assertFalse(self.destination.exists())
        self.assertTrue(Path(str(self.destination) + ".part.json").exists())

    def test_expired_link_never_promotes_rar(self):
        host = FakeRARServer(RAR, status=403)
        with self.assertRaises(RuntimeError):
            self.run_source(host)
        self.assertFalse(self.destination.exists())

    def test_range_geometry_covers_entire_file(self):
        with mock.patch.object(rar, "RANGE_BYTES", 8):
            self.assertEqual(rar._ranges(17), [(0, 7), (8, 15), (16, 16)])


if __name__ == "__main__":
    unittest.main()
