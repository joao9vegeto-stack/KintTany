#!/usr/bin/env python3
"""Regression of Dagor required-extension gate in the Switch game, not a generic VK workaround."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = "0075-vulkan-dagor-required-shader-draw-parameters.patch"


class DagorVulkanRequiredExtensionTests(unittest.TestCase):
    def test_patch_order_and_single_insertion(self):
        names = (ROOT / "patches/series").read_text().splitlines()
        self.assertEqual(names.count(PATCH), 1)
        self.assertLess(names.index("0073-vulkan-dagor-khr-physical-device-queries.patch"),
                        names.index(PATCH))
        self.assertLess(names.index("0074-vulkan-dagor-trace-physical-device-enumeration.patch"),
                        names.index(PATCH))
        patch = (ROOT / "patches" / PATCH).read_text()
        self.assertIn('"VK_KHR_bind_memory2", "VK_KHR_shader_draw_parameters"};', patch)
        self.assertIn("device suitability checks", patch)
        self.assertNotIn("VK_ERROR_INCOMPATIBLE_DRIVER = VK_SUCCESS", patch)


if __name__ == "__main__":
    unittest.main()
