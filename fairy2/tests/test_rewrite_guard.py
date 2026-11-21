#!/usr/bin/env python3
"""Regressions for recoverable, low-memory Fairy Tail 2 module rewriting."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "colab"))
import rewrite_guard as g


class RewriteGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.tmp = self.root / "patched_v65536.partial"
        self.tmp.mkdir()
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.tools = self.root / "engine/dm/tools"
        self.tools.mkdir(parents=True)
        self.key = "e" * 64
        self.src = {}
        for m in ("main", "sdk"):
            f = self.root / f"{m}.nso"
            f.write_bytes((m * 10).encode())
            self.src[m] = f

    def write_outputs(self, name):
        for suffix in g.NEEDED:
            p = self.tmp / f"{name}.{suffix}"
            if suffix == "patched.bin":
                p.write_bytes(b"PATCHED-" + name.encode())
            elif suffix == "fixups.tsv":
                p.write_text("# PATCH_OFF\t0x2000\n# BUILD_ID\tfake\n")
            else:
                p.write_text("")

    def test_completed_modules_reused_but_killed_module_restarted(self):
        self.write_outputs("sdk")
        g.save_module(self.tmp, "sdk", self.src["sdk"], self.key)
        (self.tmp / g.STATE).write_text(json.dumps({"fingerprint": self.key}))
        valid = g.prepare_partial(self.tmp, ["main", "sdk"],
                                  self.src, self.key, self.logs, self.tools)
        self.assertEqual(valid, {"sdk"})
        self.assertEqual(g.pending(["main", "sdk"], valid), ["main"])
        self.assertTrue((self.tmp / "sdk.patched.bin").is_file())

    def test_output_corruption_invalidates_only_that_module(self):
        self.write_outputs("sdk")
        g.save_module(self.tmp, "sdk", self.src["sdk"], self.key)
        (self.tmp / g.STATE).write_text(json.dumps({"fingerprint": self.key}))
        (self.tmp / "sdk.patched.bin").write_bytes(b"BAD")
        valid = g.prepare_partial(self.tmp, ["main", "sdk"],
                                  self.src, self.key, self.logs, self.tools)
        self.assertEqual(valid, set())
        self.assertFalse((self.tmp / "sdk.patched.bin").exists())

    def test_changed_fingerprint_invalidates_saved_outputs(self):
        self.write_outputs("sdk")
        g.save_module(self.tmp, "sdk", self.src["sdk"], self.key)
        (self.tmp / g.STATE).write_text(json.dumps({"fingerprint": self.key}))
        valid = g.prepare_partial(self.tmp, ["main", "sdk"],
                                  self.src, "f" * 64, self.logs, self.tools)
        self.assertEqual(valid, set())
        self.assertFalse((self.tmp / "sdk.patched.bin").exists())

    def test_legacy_three_completed_modules_salvaged_with_tool_sha(self):
        script = self.tools / "patch_nso.py"
        script.write_bytes(b"same tool version")
        record = self.tmp / "build_src.sha256"
        record.write_text(f"{hashlib.sha256(script.read_bytes()).hexdigest()}  patch_nso.py\n")
        self.write_outputs("sdk")
        (self.logs / "rewrite_sdk.log").write_text(
            "sdk patched ok cuts 0 obs 0 patch 10 PATCH_OFF 0x4000 "
            "slot_refs 7 gates 2\n")
        valid = g.prepare_partial(self.tmp, ["main", "sdk"],
                                  self.src, self.key, self.logs, self.tools)
        self.assertEqual(valid, {"sdk"})
        self.assertTrue((self.tmp / ".bio-done-sdk.json").is_file())

    def test_no_legacy_salvage_if_tool_bytes_have_changed(self):
        script = self.tools / "patch_nso.py"
        script.write_bytes(b"new tool version")
        (self.tmp / "build_src.sha256").write_text(
            f"{'a' * 64}  patch_nso.py\n")
        self.write_outputs("sdk")
        (self.logs / "rewrite_sdk.log").write_text(
            "sdk patched ok slot_refs 7 gates 2\n")
        valid = g.prepare_partial(self.tmp, ["main", "sdk"],
                                  self.src, self.key, self.logs, self.tools)
        self.assertEqual(valid, set())
        self.assertFalse((self.tmp / "sdk.patched.bin").exists())


if __name__ == "__main__":
    unittest.main()
