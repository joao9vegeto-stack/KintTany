#!/usr/bin/env python3
"""Smoke-check the regression fix for NXNative fast-refresh Vulkan translation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = "0076-build-restore-layer-shaders-options-after-from-seed.patch"


class LayerShadersOptionsTests(unittest.TestCase):
    def test_patch_is_present_after_dagor_vulkan_patches(self):
        names = (ROOT / "patches/series").read_text().splitlines()
        self.assertEqual(names.count(PATCH), 1)
        self.assertLess(names.index("0075-vulkan-dagor-required-shader-draw-parameters.patch"), names.index(PATCH))

    def test_options_and_seed_coexist(self):
        patch = (ROOT / "patches" / PATCH).read_text()
        self.assertIn("+def layer_shaders(py, repo, api, name, roots, sh, key, logs, env, mac, options=(), from_seed=False):", patch)
        self.assertIn("-def layer_shaders(py, repo, api, name, roots, sh, key, logs, env, mac, from_seed=False):", patch)
        self.assertIn("NameError: name 'options' is not defined", patch)


if __name__ == "__main__":
    unittest.main()
