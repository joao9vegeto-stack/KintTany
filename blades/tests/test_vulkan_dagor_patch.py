#!/usr/bin/env python3
"""Regressions for the three KHR entrypoints Blades of Time looked up as NULL."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = "0073-vulkan-dagor-khr-physical-device-queries.patch"


class DagorVulkanPatchTests(unittest.TestCase):
    def test_series_includes_patch_once(self):
        names = (ROOT / "patches/series").read_text().splitlines()
        self.assertEqual(names.count(PATCH), 1)
        self.assertEqual(names[-1], PATCH)

    def test_promoted_physical_device_queries_registered(self):
        data = (ROOT / "patches" / PATCH).read_text()
        for name in (
            "vkGetPhysicalDeviceQueueFamilyProperties2",
            "vkGetPhysicalDeviceFormatProperties2",
            "vkGetPhysicalDeviceSparseImageFormatProperties2",
        ):
            self.assertIn("+VK(" + name + ",", data)
        self.assertIn("h_vkGetPhysicalDeviceQueueFamilyProperties(pd", data)
        self.assertIn("h_vkGetPhysicalDeviceFormatProperties(pd", data)
        self.assertIn("(void)pd; (void)i; (void)p; *n = 0;", data)

if __name__ == "__main__":
    unittest.main()
