"""Synthetic upstream overlay tests; no game or proprietary code."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from enable_ios_offscreen_metal import edit_cmake,edit_metal
class MetalOverlayTests(unittest.TestCase):
    def test_cmake_inserts_objc_before_library(self):
        s="before\nadd_library(ps3recomp_runtime STATIC\n    fake\n)"
        r=edit_cmake(s)
        self.assertIn('enable_language(OBJC)',r)
        self.assertIn('rsx_metal_backend.m',r)
        self.assertLess(r.index('enable_language(OBJC)'),r.index('add_library'))
    def test_guard_mac_nswindow(self):
        r=edit_metal('static NSWindow*           s_window;')
        self.assertIn('#if !TARGET_OS_IPHONE\nstatic NSWindow*',r)
    def test_reject_changed_backend(self):
        with self.assertRaises(ValueError):edit_metal('static void* other;')
    def test_reject_changed_cmake(self):
        with self.assertRaises(ValueError):edit_cmake('project(untested)')
