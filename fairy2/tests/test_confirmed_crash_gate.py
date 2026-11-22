import importlib.util
import sys
import unittest
from pathlib import Path

COLAB = Path(__file__).resolve().parents[1] / "colab"
sys.path.insert(0, str(COLAB))
spec = importlib.util.spec_from_file_location("transfer_ipa", COLAB / "transfer_ipa.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class KnownDeviceCrash(unittest.TestCase):
    def test_reject_real_device_crash_run(self):
        with self.assertRaisesRegex(RuntimeError, "CRASH CONFIRMADO"):
            module.reject_confirmed_device_crash(44990224107)

    def test_reject_same_ipa_with_different_run(self):
        with self.assertRaisesRegex(RuntimeError, "CRASH CONFIRMADO"):
            module.reject_confirmed_device_crash(100000000000,
                "6faba771ab897cec3c19277a03815e42c3428be1c6c92e522195a0133db196d1")

    def test_fdata_ioprobe_crash_is_quarantined(self):
        with self.assertRaisesRegex(RuntimeError, "CRASH CONFIRMADO"):
            module.reject_confirmed_device_crash(45064035915)
        with self.assertRaisesRegex(RuntimeError, "CRASH CONFIRMADO"):
            module.reject_confirmed_device_crash(
                100000000000,
                "416b9582e27cf2ca3ae4d10e2001b07ee95717c398451766b5445efc80dd3a6e")
        self.assertIn(45064035915, module.DEVICE_CRASH_RUNS)

    def test_allow_new_candidate_for_future_validation(self):
        module.reject_confirmed_device_crash(100000000000, "f" * 64)

    def test_run_rejected_before_artifact_download(self):
        src = (COLAB / "transfer_ipa.py").read_text()
        discovery = src.split("def select_latest_successful_ipa_artifact(", 1)[1].split(
            "def verified_ipa_report(", 1)[0]
        transfer = src.split("def transfer_latest_successful_ipa(", 1)[1].split(
            "def main():", 1)[0]
        self.assertLess(discovery.index("if rid in DEVICE_CRASH_RUNS:"),
                        discovery.index('artifacts = github_get('))
        self.assertLess(transfer.index("reject_confirmed_device_crash(rid)"),
                        transfer.index("/actions/artifacts/{artifact"))
        self.assertLess(transfer.index("reject_confirmed_device_crash(rid, sha)"),
                        transfer.index("uploaded = upload("))
