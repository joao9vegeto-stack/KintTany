"""Regression tests for the X3 range control and existing launcher settings."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hooklink2ios_perf_repack as repack

class RangeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = Path(self.tmp.name)
        self.dm = self.app / "dm"
        self.dm.mkdir()
        self.config = self.dm / "launcher.json"
        self.rows = [
            {"env": "DM_FRAME_MODE", "kind": "choice", "options": [["0", "60"], ["1", "30"]], "default": "0"},
            {"env": "DM_RENDER_SCALE", "kind": "range", "min": 0.25, "max": 1.0, "step": 0.05, "default": "0.667"},
            {"env": "DM_DYNAMIC_RESOLUTION", "kind": "toggle", "on": "1", "off": "0", "default": "0"},
            {"env": "DM_PRESENT_UPSCALE", "kind": "choice", "options": [["off", "Standard"], ["metalfx", "MetalFX"]], "default": "off"},
        ]
        self.config.write_text(json.dumps({"schema": 1, "game": repack.TITLE, "settings": self.rows}))
        (self.dm / "env.txt").write_text("DM_RENDER_SCALE=1.0\nDM_OTHER=1\n")
        self.old_presets = repack.PRESETS
        self.addCleanup(setattr, repack, "PRESETS", self.old_presets)
        repack.PRESETS = {"test": {"DM_RENDER_SCALE": "0.85", "DM_DYNAMIC_RESOLUTION": "1", "DM_FRAME_MODE": "1", "DM_PRESENT_UPSCALE": "metalfx"}}

    def test_actual_x3_preset(self):
        changes = repack.PRESETS["test"]
        result = repack.patch_launcher_and_env(self.app, changes)
        self.assertEqual(result["launcher_defaults"], changes)
        self.assertEqual(result["bundled_env"], {"DM_OTHER": "1"})
        rows = json.loads(self.config.read_text())["settings"]
        self.assertEqual(rows[1]["default"], "0.85")
        self.assertEqual(rows[1]["kind"], "range")
        self.assertEqual(rows[1]["step"], 0.05)

    def test_invalid_ranges(self):
        for v in ("0.86", "0.20", "1.05", "NaN", "Infinity", "abc"):
            with self.subTest(v=v), self.assertRaises(SystemExit):
                repack.patch_launcher_and_env(self.app, {"DM_RENDER_SCALE": v})

    def test_endpoints(self):
        for v in ("0.25", "1.0"):
            with self.subTest(v=v):
                repack.patch_launcher_and_env(self.app, {"DM_RENDER_SCALE": v})
                self.assertEqual(json.loads(self.config.read_text())["settings"][1]["default"], v)

    def test_invalid_step(self):
        self.rows[1]["step"] = 0
        self.config.write_text(json.dumps({"schema": 1, "game": repack.TITLE, "settings": self.rows}))
        with self.assertRaises(SystemExit):
            repack.patch_launcher_and_env(self.app, {"DM_RENDER_SCALE": "0.85"})

if __name__ == "__main__":
    unittest.main()
