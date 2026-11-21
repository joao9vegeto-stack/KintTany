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

    def test_workflows_remain_isolated(self):
        linux = (ROOT / ".github/workflows/biomutant-main-linux.yml").read_text()
        mac = (ROOT / ".github/workflows/biomutant.yml").read_text()
        self.assertIn("paths: ['biotant/main-rewrite-request.json']", linux)
        self.assertIn("paths: ['biotant/handoff.json']", mac)
        self.assertIn("runs-on: ubuntu-latest", linux)
        self.assertNotIn("biotant/scripts/build_shared.py", linux)


if __name__ == "__main__":
    unittest.main()
