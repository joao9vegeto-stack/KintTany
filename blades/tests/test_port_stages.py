#!/usr/bin/env python3
"""Offline regression tests for Linux-first game shaders and Mac-only captures."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from port_stages import (source_flags, deferred_mac_stages, require_valid_stage_list)

spec = importlib.util.spec_from_file_location("bladestime_mac_capture", ROOT / "scripts/mac_capture.py")
assert spec and spec.loader
mac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mac)
SHA = "a" * 64


def facts(gfx="nvn", **flags):
    return {"graphics": (gfx, "detected"), **{k: (v, "survey") for k,v in flags.items()}}


def manifest(gfx="nvn", stage="linux_complete", flags=None, mac_stages=None,
             jit=False, decoded=False, key=SHA):
    return {
        "graphics": gfx, "package_version": "v65536", "shader_split_stage": stage,
        "shader_package_key": key, "source_capture_flags": flags or [],
        "mac_host_stages": mac_stages or [], "jit_required": jit,
        "linux_ue_decode_complete": decoded,
        "shader_versions": ["v65536"], "provisional": True,
    }


class FakeBuilder:
    def __init__(self, key=SHA):
        self.key = key
        self.events = []
        self.rfs = SimpleNamespace(source=lambda x: x / "RomFS.img")
    def uses_jit(self, exefs):
        return False
    def package_key(self, path):
        return self.key
    def capture_glslc(self, *args):
        self.events.append("capture_glslc")
        return {"observed_shader"}
    def check_glslc_coverage(self, observed, profile):
        self.events.append(("coverage", observed))
    def split_shaders(self, *args, **kwargs):
        self.events.append("mac_split")
        return self.key
    def capture_shaders(self, *args):
        self.events.append("capture_shaders")
        return args[3] / "gl_capture"
    def ue_stamp(self, dirname):
        return "verified"


class MacCaptureTests(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        version = root / "extract/v65536"
        (version / "ExeFS").mkdir(parents=True)
        (version / "ExeFS/main").write_bytes(b"rewritten module input")
        (version / "RomFS.img").write_bytes(b"romfs")
        (root / "shader/pkg").mkdir(parents=True)
        (root / "gl_capture").mkdir()
        return tmp, root, version

    def test_source_driven_capture_flags(self):
        self.assertEqual(source_flags(facts("nvn", glslc_capture=True, ue_decode=True)),
                         ["glslc_capture", "ue_decode"])
        self.assertEqual(deferred_mac_stages(facts("nvn")), [])
        self.assertEqual(deferred_mac_stages(facts("nvn"), jit=True), ["jit_capture"])
        self.assertEqual(deferred_mac_stages(facts("nvn", ue_decode=True),
                                              linux_ue_complete=True), [])
        self.assertEqual(deferred_mac_stages(facts("gl", gl_capture=True)),
                         ["gl_capture"])
        self.assertEqual(deferred_mac_stages(facts("vulkan", vk_capture=True)),
                         ["vk_capture"])
        with self.assertRaises(ValueError):
            deferred_mac_stages(facts("nvn"), linux_ue_complete=True)
        with self.assertRaises(ValueError):
            require_valid_stage_list(["vk_capture", "vk_capture"])

    def test_verified_linux_nvn_split_reused(self):
        temp, root, version = self.fixture()
        try:
            builder = FakeBuilder()
            pkg, captures = mac.complete(
                builder, root, version, root / "patched", root, {}, root,
                object(), manifest(), "python3", facts())
            self.assertEqual(pkg, SHA)
            self.assertEqual(captures, [])
            self.assertEqual(builder.events, [])
        finally:
            temp.cleanup()

    def test_mac_capture_precedes_dependent_nvn_shader_split(self):
        temp, root, version = self.fixture()
        try:
            builder = FakeBuilder()
            f = facts("nvn", glslc_capture=True)
            prep = manifest(stage="mac_pending", key=None,
                            flags=["glslc_capture"], mac_stages=["glslc_capture"])
            pkg, _ = mac.complete(builder, root, version, root / "patched",
                                  root, {}, root, object(), prep, "python3", f)
            self.assertEqual(pkg, SHA)
            self.assertEqual(builder.events, ["capture_glslc", "mac_split",
                             ("coverage", {"observed_shader"})])
        finally:
            temp.cleanup()

    def test_gl_capture_is_native_only_and_no_nvn_split(self):
        temp, root, version = self.fixture()
        try:
            builder = FakeBuilder()
            f = facts("gl", gl_capture=True)
            prep = manifest("gl", "metal_deferred", key=None,
                            flags=["gl_capture"], mac_stages=["gl_capture"])
            pkg, capture_dirs = mac.complete(builder, root, version,
                                            root / "patched", root, {}, root,
                                            object(), prep, "python3", f)
            self.assertIsNone(pkg)
            self.assertEqual(capture_dirs, [root / "gl_capture"])
            self.assertEqual(builder.events, ["capture_shaders"])
        finally:
            temp.cleanup()

    def test_linux_ue_decoded_never_redone_on_mac(self):
        temp, root, version = self.fixture()
        try:
            folder = version / "ue_shaders"
            folder.mkdir()
            (folder / "stamp").write_text("verified")
            builder = FakeBuilder()
            f = facts("nvn", ue_decode=True)
            prep = manifest(flags=["ue_decode"], decoded=True)
            pkg, _ = mac.complete(builder, root, version, root / "patched",
                                  root, {}, root, object(), prep, "python3", f)
            self.assertEqual(pkg, SHA)
            self.assertEqual(builder.events, [])
        finally:
            temp.cleanup()

    def test_fabricated_completed_shader_key_is_rejected(self):
        temp, root, version = self.fixture()
        try:
            builder = FakeBuilder(key="b"*64)
            with self.assertRaises(RuntimeError):
                mac.complete(builder, root, version, root / "patched",
                             root, {}, root, object(), manifest(), "python3", facts())
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
