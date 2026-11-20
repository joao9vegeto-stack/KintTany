#!/usr/bin/env python3
"""Dagor movie viewport and SqPlus fatal diagnostic regression checks."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = "0077-vulkan-dagor-log-viewport-scissor-size.patch"

class DagorMovieDiagnostics(unittest.TestCase):
    def test_bounded_viewport_log_patch(self):
        series = (ROOT / "patches/series").read_text().splitlines()
        self.assertEqual(series.count(PATCH), 1)
        self.assertLess(series.index("0076-build-restore-layer-shaders-options-after-from-seed.patch"), series.index(PATCH))
        patch = (ROOT / "patches" / PATCH).read_text()
        self.assertIn('VLOG("diag viewport:', patch)
        self.assertIn('VLOG("diag scissor:', patch)
        self.assertIn("atomic_fetch_add(&shown, 1) < 12", patch)
        self.assertNotIn("VLOG(\"diag viewport", patch.split("@@")[0])

    def test_capture_traces_guest_squirrel_and_file_errors(self):
        source = (ROOT / "blades/scripts/mac_capture.py").read_text()
        self.assertIn('DM_DBG="1"', source)
        self.assertIn('DM_FS="1"', source)
        wf = (ROOT / ".github/workflows/bladestime.yml").read_text()
        self.assertIn("BladesTime-capture-diagnostics-", wf)
        self.assertIn("vk_capture.log", wf)

if __name__ == "__main__":
    unittest.main()
