#!/usr/bin/env python3
"""Offline tests: main-only Linux Actions diversion, no game or credentials."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "biotant" / "colab"))
sys.path.insert(0, str(ROOT / "biotant" / "scripts"))
import offload_main as m
import main_rewrite_linux as runner


class MainOffloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_relocation_does_not_change_matching_source_dependencies(self):
        r = self.dir / "old.sha256"
        w = self.dir / "new.sha256"
        key = "a" * 64
        key2 = "b" * 64
        r.write_text(f"{key}  ../../../old/dm/tools/patch_nso.py\n"
                     f"{key2}  ../../old/provisional/patches.py\n")
        w.write_text(f"{key2}  ../../runner/provisional/patches.py\n"
                     f"{key}  dm/tools/patch_nso.py\n")
        self.assertEqual(runner.dependency_entries(r), runner.dependency_entries(w))
        w.write_text(f"{key}  dm/tools/patch_nso.py\n"
                     f"{'c'*64}  ../../runner/provisional/patches.py\n")
        self.assertNotEqual(runner.dependency_entries(r), runner.dependency_entries(w))

    def test_corrupt_dependency_inventory_rejected(self):
        f = self.dir / "bad.sha256"
        f.write_text("not-a-digest  patch_nso.py\n")
        with self.assertRaisesRegex(RuntimeError, "Corrupt"):
            runner.dependency_entries(f)

    @unittest.skipUnless(shutil.which("zstd"), "zstd not installed in test runtime")
    def test_transport_roundtrip_uses_private_archive(self):
        stage = self.dir / "stage"
        stage.mkdir()
        (stage / "main.nso").write_bytes(b"NSO0" + bytes(range(128)))
        profile = stage / "profile" / m.TITLE_ID
        profile.mkdir(parents=True)
        (profile / "game.tsv").write_text("modules\tmain sdk\n")
        (stage / "input.json").write_text('{"format":1}')
        source_archive = self.dir / "input.tar.zst"
        m.pack_zstd(stage, source_archive)
        result = self.dir / "unpacked"
        m.unpack_zstd(source_archive, result)
        for name in ("main.nso", "input.json", f"profile/{m.TITLE_ID}/game.tsv"):
            self.assertEqual((stage / name).read_bytes(), (result / name).read_bytes())

    @unittest.skipUnless(shutil.which("zstd"), "zstd not installed in test runtime")
    def test_path_traversal_output_archive_rejected(self):
        tar = self.dir / "unsafe.tar"
        with tarfile.open(tar, "w") as archive:
            data = b"STOLEN"
            info = tarfile.TarInfo("../outside.txt")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        compressed = self.dir / "unsafe.tar.zst"
        subprocess.run(["zstd", "-q", "-f", "-o", str(compressed), str(tar)], check=True)
        with self.assertRaisesRegex(RuntimeError, "Unsafe"):
            m.unpack_zstd(compressed, self.dir / "safe")
        self.assertFalse((self.dir / "outside.txt").exists())

    def test_service_account_updates_existing_user_owned_file_not_creates(self):
        path = self.dir / "main-result-id.tar.zst"
        path.write_bytes(b"known output")
        size = path.stat().st_size
        md5 = __import__("hashlib").md5(path.read_bytes()).hexdigest()
        result = {"id": "owned-file", "name": path.name,
                  "size": str(size), "md5Checksum": md5}

        class Action:
            def __init__(self, item):
                self.item = item
            def execute(self):
                return self.item
            def next_chunk(self, **kwargs):
                return None, self.item

        class Files:
            def get(self, **kwargs):
                self.get_args = kwargs
                return Action({"id": "owned-file", "name": path.name,
                               "size": str(len(runner.PENDING)),
                               "md5Checksum": __import__("hashlib").md5(runner.PENDING).hexdigest(),
                               "parents": ["owned-folder"]})
            def update(self, **kwargs):
                self.update_args = kwargs
                return Action(result)
            def create(self, **kwargs):
                raise AssertionError("Service account must not create in My Drive")

        class Api:
            def __init__(self):
                self.f = Files()
            def files(self):
                return self.f

        api = Api()
        runner.upload(api, "owned-folder", "owned-file", path, path.name)
        self.assertEqual(api.f.update_args["fileId"], "owned-file")
        self.assertNotIn("body", api.f.update_args)
        # The real failure after the successful 5-minute main rewrite: the
        # upload() metadata get forgot to request md5Checksum, yet later
        # required its value. Prevent another costly repeat of this bug.
        self.assertIn("md5Checksum", api.f.get_args["fields"])
        self.assertIn("capabilities(canEdit)", api.f.get_args["fields"])

    def test_drive_write_probe_runs_before_rewrite(self):
        identity = {"output_file_id": "owned-file",
                    "folder_id": "owned-folder",
                    "output_file_name": "main-result-abc.tar.zst"}
        marker_md5 = __import__("hashlib").md5(runner.PENDING).hexdigest()
        events = []
        class Response:
            def __init__(self, obj):
                self.obj = obj
            def execute(self):
                return self.obj
        class Api:
            def files(self):
                return self
            def get(self, **kwargs):
                events.append("get")
                return Response({"id": "owned-file", "name": identity["output_file_name"],
                                 "size": "0", "parents": ["owned-folder"],
                                 "capabilities": {"canEdit": True}})
            def update(self, **kwargs):
                events.append("update")
                self.file_id = kwargs["fileId"]
                return Response({"id": "owned-file", "name": identity["output_file_name"],
                                 "size": len(runner.PENDING), "md5Checksum": marker_md5})
            def create(self, **kwargs):
                raise AssertionError("Probe may not create a Drive file")
        api = Api()
        runner.verify_drive_output_writable(api, identity)
        self.assertEqual(events, ["get", "update"])
        self.assertEqual(api.file_id, "owned-file")

    def test_workflows_remain_isolated(self):
        linux = (ROOT / ".github/workflows/biomutant-main-linux.yml").read_text()
        mac = (ROOT / ".github/workflows/biomutant.yml").read_text()
        self.assertIn("paths: ['biotant/main-rewrite-request.json']", linux)
        self.assertIn("paths: ['biotant/handoff.json']", mac)
        self.assertIn("runs-on: ubuntu-latest", linux)
        self.assertNotIn("biotant/scripts/build_shared.py", linux)


if __name__ == "__main__":
    unittest.main()
