"""Regression tests for the real BladesTime Route C frame-rate menu."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_shared.py"
spec = importlib.util.spec_from_file_location("bladestime_fps_build", SCRIPT)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class FrameRateMenuTest(unittest.TestCase):
    def test_menu_preserves_30_and_offers_60(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "launcher.json"
            path.write_text(json.dumps({"schema": 1, "game": build.TITLE_ID, "settings": [
                {"env": "DM_OPMODE", "kind": "choice", "default": "1",
                 "options": [["1", "Na base"], ["0", "Portátil"]]}]}))
            build.configure_bladestime_frame_rate_menu(Path(folder))
            rows = json.loads(path.read_text())["settings"]
            self.assertEqual([x["env"] for x in rows], ["DM_OPMODE", "DM_FPS"])
            self.assertEqual(rows[1]["default"], "30")
            self.assertEqual([x[0] for x in rows[1]["options"]], ["30", "60"])

    def test_rejects_wrong_game_and_duplicate_fps(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "launcher.json"
            for game, settings in (("0000000000000000", []),
                                   (build.TITLE_ID, [{"env": "DM_FPS_TARGET"}])):
                path.write_text(json.dumps({"schema": 1, "game": game, "settings": settings}))
                with self.assertRaises(SystemExit):
                    build.configure_bladestime_frame_rate_menu(Path(folder))


if __name__ == "__main__":
    unittest.main()
