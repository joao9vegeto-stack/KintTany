import importlib.util
import unittest
from pathlib import Path

MOD = Path(__file__).resolve().parents[1] / "scripts/repack_ipa.py"
spec = importlib.util.spec_from_file_location("fairy_crash_repack", MOD)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CrashProbeRepackTests(unittest.TestCase):
    def settings(self):
        game={"game":"0100B9801F872000","settings":[
            {"env":"DM_OPMODE","kind":"choice","default":"1","options":[["1","Docked"]]}]}
        module.configure_launcher(game)
        module.validate_settings(game)
        return {x["env"]:x for x in game["settings"]}

    def test_no_engine_fps_removed(self):
        s=self.settings()
        self.assertEqual(s["DM_FPS_TARGET"]["default"],"30")
        self.assertEqual([v[0] for v in s["DM_FPS_TARGET"]["options"]],["30","60"])
    def test_ab_swap_kept(self):
        self.assertEqual(self.settings()["DM_PAD_MAP"]["on"],"A=B,B=A")
    def test_memory_probe_on(self):
        self.assertEqual(self.settings()["DM_SVC"]["default"],"1")
    def test_idempotent(self):
        g={"game":"0100B9801F872000","settings":[{"env":"DM_OPMODE"}]}
        module.configure_launcher(g)
        module.configure_launcher(g)
        self.assertEqual(len(g["settings"]),len({x["env"] for x in g["settings"]}))
    def test_other_game_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"another game's launcher"):
            module.configure_launcher({"game":"0100B9801F872001","settings":[]})
