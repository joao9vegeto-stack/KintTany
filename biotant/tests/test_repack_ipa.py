"""Biomutant resource-only IPA repack; no game assets or Apple host required."""
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "biotant/scripts/repack_ipa.py"
spec = importlib.util.spec_from_file_location("biomutant_light_repack", MODULE)
repack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repack)


def fake_macho(path, code=b"immutable compiled code" * 19, sig=b"old signature"):
    """Minimal structurally valid 64-bit Mach-O with one __TEXT,__text."""
    ncmds = 1
    cmdsize = 72 + 80
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, 0x100000C, 0, 2,
                         ncmds, cmdsize, 0, 0)
    section_off = 32 + cmdsize
    seg = struct.pack("<II16sQQQQiiII", 0x19, cmdsize,
                      b"__TEXT".ljust(16, b"\x00"), 0, 0, 0,
                      section_off + len(code), 7, 5, 1, 0)
    sect = struct.pack("<16s16sQQIIIIIIII", b"__text".ljust(16, b"\x00"),
                       b"__TEXT".ljust(16, b"\x00"), 0,
                       len(code), section_off, 2, 0, 0, 0, 0, 0, 0)
    path.write_bytes(header + seg + sect + code + sig)


class LightweightRepackTests(unittest.TestCase):
    def test_unreal_fps_and_ab_swap_are_real_engine_environment_keys(self):
        sample = {"schema": 1, "game": repack.TITLE, "settings": [
            {"env": "DM_OPMODE", "kind": "choice", "default": "1",
             "options": [["0", "handheld"], ["1", "docked"]]},
            {"env": "DM_FPS", "kind": "choice", "default": "30",
             "options": [["30", "30 FPS"], ["60", "60 FPS"]]},
            {"env": "DM_SHOW_FPS", "kind": "toggle", "default": "0"},
        ]}
        changed = repack.configure_launcher(sample)
        self.assertTrue(repack.validate_settings(changed))
        envs = [s["env"] for s in changed["settings"]]
        self.assertEqual(envs, ["DM_OPMODE", "DM_FPS_TARGET", "DM_PAD_MAP",
                                "DM_SHOW_FPS"])
        self.assertNotIn("DM_FPS", envs)
        fps = changed["settings"][1]
        self.assertEqual([x[0] for x in fps["options"]], ["30", "60"])
        mapping = changed["settings"][2]
        self.assertEqual(mapping["on"], "A=B,B=A")
        self.assertEqual(mapping["off"], "")

    def test_idempotence_preserves_all_other_game_choices(self):
        v = {"game": repack.TITLE, "schema": 1,
             "settings": [{"env": "DM_OPMODE", "kind": "choice",
                           "options": [["1", "Dock"]], "default": "1"}]}
        first = repack.configure_launcher(v)
        second = repack.configure_launcher(json.loads(json.dumps(first)))
        self.assertEqual(first, second)
        self.assertEqual(len(second["settings"]), 3)

    def test_other_games_refused(self):
        with self.assertRaisesRegex(RuntimeError, "another game"):
            repack.configure_launcher({"game": "FFFFFFFFFFFFFFFF", "settings": []})

    def test_native_machine_code_unchanged_after_signature_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b, c = [Path(temp) / x for x in ("before", "signed", "modified")]
            fake_macho(a, sig=b"old signature blob")
            fake_macho(b, sig=b"larger new signature blob")
            fake_macho(c, code=b"modified compiled code" * 19)
            self.assertEqual(repack.macho_text_sha(a), repack.macho_text_sha(b))
            self.assertNotEqual(repack.macho_text_sha(a), repack.macho_text_sha(c))

    def test_pipeline_never_invokes_full_game_compiler(self):
        workflow = (ROOT / ".github/workflows/biomutant-repack.yml").read_text()
        self.assertIn("44880915730", workflow)
        self.assertIn("biotant/scripts/repack_ipa.py", workflow)
        self.assertNotIn("build_shared.py", workflow)
        self.assertNotIn("xcodebuild", workflow)
        self.assertNotIn("build_shaders", workflow)
        self.assertNotIn("build_ipa.sh", workflow)
        self.assertNotIn("prepare_actions.py", workflow)


if __name__ == "__main__":
    unittest.main()
