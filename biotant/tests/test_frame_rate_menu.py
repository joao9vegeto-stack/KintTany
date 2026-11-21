"""Regression tests for the real BioiOSMutant Route C frame-rate menu."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_shared.py"
spec = importlib.util.spec_from_file_location("biomutant_fps_build", SCRIPT)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class FrameRateMenuTest(unittest.TestCase):
    def test_menu_preserves_30_and_offers_60(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "game.manifest.json"
            manifest.write_text(json.dumps({"title_id": build.TITLE_ID, "launcher": "dm/launcher.json"}))
            path = Path(folder) / "dm" / "launcher.json"
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps({"schema": 1, "game": build.TITLE_ID, "settings": [
                {"env": "DM_OPMODE", "kind": "choice", "default": "1",
                 "options": [["1", "Na base"], ["0", "Portátil"]]}]}))
            build.configure_biomutant_frame_rate_menu(Path(folder))
            rows = json.loads(path.read_text())["settings"]
            self.assertEqual([x["env"] for x in rows], ["DM_OPMODE", "DM_FPS_TARGET", "DM_PAD_MAP"])
            self.assertEqual(rows[1]["default"], "30")
            self.assertEqual([x[0] for x in rows[1]["options"]], ["30", "60"])
            self.assertEqual(rows[2]["kind"], "toggle")
            self.assertEqual(rows[2]["on"], "A=B,B=A")
            self.assertEqual(rows[2]["off"], "")

    def test_rejects_bad_manifest_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "game.manifest.json").write_text(json.dumps({
                "title_id": build.TITLE_ID, "launcher": "launcher.json"}))
            (root / "launcher.json").write_text(json.dumps({
                "schema": 1, "game": build.TITLE_ID, "settings": []}))
            with self.assertRaises(SystemExit):
                build.configure_biomutant_frame_rate_menu(root)

    def test_rejects_wrong_game_and_duplicate_fps(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "game.manifest.json"
            manifest.write_text(json.dumps({"title_id": build.TITLE_ID, "launcher": "dm/launcher.json"}))
            path = Path(folder) / "dm" / "launcher.json"
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps({"schema": 1, "game": "0000000000000000", "settings": []}))
            with self.assertRaises(SystemExit):
                build.configure_biomutant_frame_rate_menu(Path(folder))
            # Earlier builds had the presentation-only DM_FPS selector.
            # It must be upgraded, not duplicated or left active.
            path.write_text(json.dumps({"schema": 1, "game": build.TITLE_ID, "settings": [
                {"env": "DM_FPS", "kind": "choice", "default": "30",
                 "options": [["30", "30 FPS"], ["60", "60 FPS"]]}
            ]}))
            build.configure_biomutant_frame_rate_menu(Path(folder))
            updated = json.loads(path.read_text())
            self.assertNotIn("DM_FPS", [x["env"] for x in updated["settings"]])
            self.assertEqual([x["env"] for x in updated["settings"]],
                             ["DM_FPS_TARGET", "DM_PAD_MAP"])


if __name__ == "__main__":
    unittest.main()
