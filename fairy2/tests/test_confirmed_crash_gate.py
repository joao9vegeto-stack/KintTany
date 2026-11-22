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

    def test_allow_new_candidate_for_future_validation(self):
        module.reject_confirmed_device_crash(100000000000, "f" * 64)

    def test_run_rejected_before_artifact_download(self):
        src = (COLAB / "transfer_ipa.py").read_text()
        body = src.split("def try_transfer_global_memory():",1)[1].split("def transfer_original_explicit():",1)[0]
        self.assertLess(body.index('reject_confirmed_device_crash(newest["id"])'),
                        body.index('artifacts = get('))
        self.assertLess(body.index('reject_confirmed_device_crash(newest["id"], digest)'),
                        body.index('uploaded = upload('))
