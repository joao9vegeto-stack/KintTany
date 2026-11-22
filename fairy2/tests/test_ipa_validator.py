"""Synthetic regression tests; no NSP, iOS build or network access needed."""
import json
import plistlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "colab"))
from ipa_validator import validate_ipa

FR = "DmGame0100B9801F872000.framework"
APP = "Payload/DmShell.app/"
FW = APP + "Frameworks/" + FR + "/"
REPORT = {"framework": FR, "shader_payload": {
    "ipa_path": "Frameworks/" + FR + "/msl/b-test.img", "size_bytes": 5}}

def make_ipa(path, *, outer=False, missing_payload=False, broken_pad=False):
    with zipfile.ZipFile(path, "w", allowZip64=True) as z:
        if outer:
            z.writestr("Fairy2iOS-FairyTail2.ipa", b"nested but not extracted")
            return
        app = "Another/" if missing_payload else APP
        fw = app + "Frameworks/" + FR + "/"
        z.writestr(app + "Info.plist", plistlib.dumps({
            "CFBundleExecutable": "DmShell",
            "CFBundleIdentifier": "org.nxnative.fairy2.0100b9801f872000"}))
        z.writestr(app + "DmShell", b"0"*8192)
        z.writestr(fw + "game.manifest.json", json.dumps({"title_id": "0100B9801F872000"}))
        z.writestr(fw + "dm/launcher.json", json.dumps({
            "game": "0100B9801F872000", "settings": [
                {"env": "DM_FPS_TARGET", "default": "30",
                 "options": [["30", "30 FPS"], ["60", "60 FPS"]]},
                {"env": "DM_PAD_MAP", "on": "wrong" if broken_pad else "A=B,B=A"}]}))
        z.writestr(fw + "msl/b-test.img", b"12345")

class IpaValidationTests(unittest.TestCase):
    def exercise(self, **kw):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "Test.ipa"
        make_ipa(path, **kw)
        return validate_ipa(path, REPORT)
    def test_valid_ipa(self):
        self.assertTrue(self.exercise()["swap_ab"])
    def test_reject_outer_artifact(self):
        with self.assertRaisesRegex(RuntimeError, "Payload"):
            self.exercise(outer=True)
    def test_reject_missing_payload(self):
        with self.assertRaisesRegex(RuntimeError, "Payload"):
            self.exercise(missing_payload=True)
    def test_reject_broken_settings(self):
        with self.assertRaisesRegex(RuntimeError, "A/B"):
            self.exercise(broken_pad=True)

if __name__ == "__main__":
    unittest.main()
