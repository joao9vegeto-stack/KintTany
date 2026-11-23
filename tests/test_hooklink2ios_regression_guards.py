#!/usr/bin/env python3
"""Host-only regression guards for HookLink2iOS's X3 graphics rollback."""
import importlib.util
from pathlib import Path
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hooklink2ios_backport_native.py"
REPACK = ROOT / "scripts" / "hooklink2ios_perf_repack.py"

class RenderingRegressionTests(unittest.TestCase):
    def test_x3_whole_chain_bypass_is_opt_in_not_default(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('static int up_chain_enabled(void)', source)
        self.assertIn('mode = e && !strcmp(e, "1");', source)
        self.assertIn('up_chain_enabled() && up_mfx_on()', source)
        self.assertIn('OFF (legacy rendering compatibility)', source)
        self.assertNotIn('int role = up_mfx_on() && !g_up_chain_refused', source)

    def test_memory_guard_and_30_60fps_presets(self):
        spec = importlib.util.spec_from_file_location("hooklink_repack_guard", REPACK)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertEqual(set(m.PRESETS), {"stable30","balanced30fg","native60"})
        for name, preset in m.PRESETS.items():
            self.assertEqual(preset["DM_HOOKLINK_X3_CHAIN"], "0", name)
            self.assertEqual(preset["DM_NVN_WS_MB"], "4800", name)
            self.assertEqual(preset["DM_UPSCALER"], "metalfx", name)
        self.assertEqual(m.PRESETS["native60"]["DM_FPS_TARGET"], "60")
        self.assertEqual(m.PRESETS["balanced30fg"]["DM_FRAMEGEN"], "1")

    def test_new_runtime_guards_not_forced_into_launcher(self):
        spec = importlib.util.spec_from_file_location("hooklink_repack_guard2", REPACK)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp)
            (app / "dm").mkdir()
            rows = [
                {"env":"DM_FRAME_MODE","kind":"choice","default":"0","options":[["0","60"],["1","30"],["2","30+FG"]]},
                {"env":"DM_FPS_TARGET","kind":"choice","default":"60","options":[["30","30"],["60","60"]]},
                {"env":"DM_FRAMEGEN","kind":"toggle","default":"0","on":"1","off":"0"},
                {"env":"DM_DYNAMIC_RESOLUTION","kind":"toggle","default":"1","on":"1","off":"0"},
                {"env":"DM_UPSCALER","kind":"choice","default":"game","options":[["metalfx","MetalFX"],["game","Game"]]}
            ]
            (app / "dm" / "launcher.json").write_text(json.dumps({"schema":1,"game":m.TITLE,"settings":rows}))
            (app / "dm" / "env.txt").write_text("DM_NVN_WS_MB=8000\nDM_HOOKLINK_X3_CHAIN=1\n")
            report = m.patch_launcher_and_env(app, m.PRESETS["balanced30fg"])
            self.assertEqual(report["bundled_env"]["DM_NVN_WS_MB"], "4800")
            self.assertEqual(report["bundled_env"]["DM_HOOKLINK_X3_CHAIN"], "0")
            self.assertNotIn("DM_FRAME_MODE", report["bundled_env"])
            self.assertEqual(report["launcher_defaults"]["DM_FRAME_MODE"], "2")

if __name__ == "__main__":
    unittest.main()
