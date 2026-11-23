#!/usr/bin/env python3
"""Unit tests for the no-shader HookLink2iOS repack; no macOS or game data needed."""
import importlib.util
import json
import plistlib
import tempfile
import unittest
import zipfile
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts" / "hooklink2ios_perf_repack.py"
spec = importlib.util.spec_from_file_location("hooklink_repack", PATH)
repack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repack)

class RepackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = Path(self.tmp.name) / "Payload" / "DmIOS.app"
        (self.app/"dm").mkdir(parents=True)
        self.config = {"schema":1,"game":repack.TITLE,"settings":[
            {"env":"DM_FRAME_MODE","kind":"choice","default":"0","options":[["0","60"],["1","30"],["2","30 + FG"]]},
            {"env":"DM_FPS_TARGET","kind":"choice","default":"60","options":[["30","30"],["60","60"]]},
            {"env":"DM_FRAMEGEN","kind":"toggle","default":"0","on":"1","off":"0"},
            {"env":"DM_UPSCALER","kind":"choice","default":"metalfx","options":[["metalfx","MetalFX"],["game","Game"]]},
            {"env":"DM_FRAMEGEN_SCALE","kind":"choice","default":"1","options":[["1","Full"],["0.75","Lighter"]]},
            {"env":"DM_SHOW_FPS","kind":"toggle","default":"0","on":"1","off":"0"},
            {"env":"DM_DYNAMIC_RESOLUTION","kind":"toggle","default":"1","on":"1","off":"0"}
        ]}
        (self.app/"dm"/"launcher.json").write_text(json.dumps(self.config))
        (self.app/"dm"/"env.txt").write_text("DM_FRAME_MODE=0\nDM_UPSCALER=game\nDM_QOS_MAP=1\nDM_RT_COMP=12\n")
    def defaults(self):
        return {row["env"]:row["default"] for row in json.loads((self.app/"dm"/"launcher.json").read_text())["settings"]}
    def test_balanced_is_selectable_and_uses_metalfx(self):
        changes = repack.patch_launcher_and_env(self.app,repack.PRESETS["balanced30fg"])
        got = self.defaults()
        self.assertEqual(got["DM_FRAME_MODE"],"2")
        self.assertEqual(got["DM_FRAMEGEN"],"1")
        self.assertEqual(got["DM_FPS_TARGET"],"30")
        self.assertEqual(got["DM_FRAMEGEN_SCALE"],"0.75")
        self.assertEqual(got["DM_UPSCALER"],"metalfx")
        env = (self.app/"dm"/"env.txt").read_text()
        self.assertIn("DM_QOS_MAP=1",env)
        self.assertIn("DM_RT_COMP=auto",env)
        self.assertNotIn("DM_FRAME_MODE=",env)
        self.assertNotIn("DM_UPSCALER=",env)
        self.assertEqual(changes["launcher_defaults"]["DM_SHOW_FPS"],"1")
    def test_native60_is_selectable(self):
        repack.patch_launcher_and_env(self.app,repack.PRESETS["native60"])
        got = self.defaults()
        self.assertEqual((got["DM_FRAME_MODE"],got["DM_FPS_TARGET"],got["DM_FRAMEGEN"]),("0","60","0"))
    def test_30_without_frame_generation(self):
        repack.patch_launcher_and_env(self.app,repack.PRESETS["stable30"])
        got = self.defaults()
        self.assertEqual((got["DM_FRAME_MODE"],got["DM_FPS_TARGET"],got["DM_FRAMEGEN"]),("1","30","0"))
    def test_missing_launcher_is_fatal(self):
        (self.app/"dm"/"launcher.json").unlink()
        with self.assertRaises(SystemExit):
            repack.patch_launcher_and_env(self.app,repack.PRESETS["native60"])
    def test_unavailable_mode_is_fatal(self):
        self.config["settings"][0]["options"]=[["0","60"],["1","30"]]
        (self.app/"dm"/"launcher.json").write_text(json.dumps(self.config))
        with self.assertRaises(SystemExit):
            repack.patch_launcher_and_env(self.app,repack.PRESETS["balanced30fg"])
    def test_zip_validates_real_romfs_identity_and_metal_image(self):
        p=Path(self.tmp.name)/"sample.ipa"
        with zipfile.ZipFile(p,"w") as z:
            z.writestr(repack.PREFIX+"Info.plist",plistlib.dumps({"MinimumOSVersion":"26.0","CFBundleIdentifier":"org.nxnative.0400486024dec000"}))
            z.writestr(repack.PREFIX+"DmIOS",b"test binary")
            z.writestr(repack.PREFIX+"romfs.id",f"DMROMFSID1 title={repack.TITLE} version=v131072 build=legacy size=123 index=0000000000000123")
            z.writestr(repack.PREFIX+"msl/b-test.img",b"test shader image")
        with zipfile.ZipFile(p) as z:
            marker,shaders=repack.audit(z)
            self.assertTrue(marker.startswith("DMROMFSID1 "))
            self.assertEqual(len(shaders),1)

if __name__=="__main__":
    unittest.main()
