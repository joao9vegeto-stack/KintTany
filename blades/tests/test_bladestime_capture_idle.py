"""Regression of the title-scoped extended shader capture interval."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = "0080-bladestime-extend-vulkan-capture-through-intro.patch"

class LongIntroCaptureTest(unittest.TestCase):
    def test_long_idle_window_applies_only_to_bladestime_vulkan(self):
        p = (ROOT / "patches" / PATCH).read_text()
        self.assertIn("api == 'vk' and g.id.upper() == '0100CFA00CC74000'", p)
        self.assertIn("else 20", p)
        self.assertIn("idle_s = 90", p)
        self.assertIn("last['t'] > idle_s", p)
        self.assertNotIn("CAPTURE_SECS = 180", p)
        series = (ROOT / "patches/series").read_text().splitlines()
        self.assertEqual(series.count(PATCH), 1)
        self.assertLess(series.index("0079-bladestime-docked-dagor-viewport-720p.patch"), series.index(PATCH))

if __name__ == "__main__":
    unittest.main()
