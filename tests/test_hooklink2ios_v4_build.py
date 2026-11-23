#!/usr/bin/env python3
"""V4 upgrade integrity: do not mistake a host-only X3 backport for HookLink 4.0."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import copy
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hl4", ROOT / "scripts/hooklink2ios_v4_build.py")
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)

class MigrationTests(unittest.TestCase):
    def base(self):
        return {
            "project":"HookLink2iOS", "branch":"HookLink2iOS",
            "schema":2,"title_id":v4.TITLE,"package_version":v4.VERSION,
            "engine":{"commit":v4.ORIGINAL_PIN},
            "gpu_arch":"none",
            "nup":{"id":"nup1","size":25622267860,"sha256":"a"*64},
            "romfs":{"id":"romfs1","size":26247576430,"sha256":"b"*64,
                     "identity":f"DMROMFSID1 title={v4.TITLE} version={v4.VERSION} build={v4.ORIGINAL_PIN} size=26247576430 index=b6a3def414e47ca5"},
            "resolution_overlay":{"id":"overlay1","size":110383,"sha256":"c"*64},
        }
    def test_source_manifest_is_not_mistaken_for_ready_x3_shaders(self):
        original=self.base()
        modern=v4.upgraded_manifest(original)
        self.assertEqual(original["engine"]["commit"],v4.ORIGINAL_PIN)
        self.assertEqual(modern["engine"]["commit"],v4.UPSTREAM_PIN)
        self.assertEqual(modern["v4_migration"]["shader_rebuild_required"],True)
        self.assertEqual(modern["nup"],original["nup"])
        self.assertIn(v4.UPSTREAM_PIN,modern["romfs"]["identity"])
    def test_wrong_title_or_corrupt_nup_sha_refused(self):
        manifest=self.base()
        manifest["title_id"]="NOT_THIS_GAME"
        with self.assertRaisesRegex(RuntimeError,"wrong update/title"):v4.upgraded_manifest(manifest)
        manifest=self.base()
        manifest["nup"]["sha256"]="0"
        with self.assertRaisesRegex(RuntimeError,"invalid verified nup"):v4.upgraded_manifest(manifest)
    def test_shader_cache_generation_is_new(self):
        source=(ROOT/"scripts/hooklink2ios_v4_build.py").read_text(encoding="utf-8")
        self.assertIn('cas-{CHAIN}.db', source)
        self.assertIn('DMSH_TARGETS": "mac,ios"', source)
        self.assertIn('original_1_8_shader_image_reused"] = False',source)
        self.assertIn('DM_NVN_TEX_MIP_SKIP',source)
        self.assertNotEqual(v4.UPSTREAM_PIN,v4.ORIGINAL_PIN)

if __name__=="__main__":
    unittest.main()
