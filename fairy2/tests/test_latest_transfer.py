"""Regression tests for newest successful Fairy2iOS IPA discovery and Colab transfer."""
from pathlib import Path
import importlib.util
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "colab"))
script = ROOT / "colab" / "transfer_ipa.py"
spec = importlib.util.spec_from_file_location("fairy2_latest_transfer_regression", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run(run_id, created, name="Fairy2iOS - test", branch="Fairy2iOS"):
    return {"id": run_id, "created_at": created, "head_branch": branch, "name": name,
            "status": "completed", "conclusion": "success",
            "head_sha": "a" * 40}


def artifact(run_id, name="Fairy2iOS-Resource-7", size=1622004849,
             expired=False, sha="a" * 40):
    return {"id": run_id + 10, "name": name, "size_in_bytes": size,
            "expired": expired,
            "workflow_run": {"id": run_id, "head_sha": sha}}


class RepackTransferRegression(unittest.TestCase):
    def test_choose_latest_across_different_workflows(self):
        newest, older = run(999990001, "2026-11-22T22:00:00Z"), run(999990000, "2026-11-22T21:00:00Z")
        def api(path, params=None):
            if path == "/actions/runs":
                return {"workflow_runs": [older, newest]}
            return {"artifacts": [artifact(newest["id"] if str(newest["id"]) in path
                                           else older["id"])]}
        selected, item, skipped = module.select_latest_successful_ipa_artifact(api)
        self.assertEqual(selected["id"], newest["id"])
        self.assertEqual(item["workflow_run"]["id"], newest["id"])
        self.assertEqual(skipped, [])

    def test_crash_quarantine_and_diagnostics_rejected(self):
        broken = run(45050364099, "2026-11-22T22:00:00Z")
        info = run(999990002, "2026-11-22T21:30:00Z")
        good = run(999990001, "2026-11-22T21:00:00Z")
        def api(path, params=None):
            if path == "/actions/runs":
                return {"workflow_runs": [broken, info, good]}
            if str(info["id"]) in path:
                return {"artifacts": [artifact(info["id"], "Fairy2iOS-diagnostics-9")]}
            return {"artifacts": [artifact(good["id"])]}
        selected, _, skipped = module.select_latest_successful_ipa_artifact(api)
        self.assertEqual(selected["id"], good["id"])
        self.assertIn(45050364099, skipped)

    def test_no_unverified_fallback_to_original(self):
        def api(path, params=None):
            if path == "/actions/runs":
                return {"workflow_runs": [run(45050364099, "2026-11-22T22:00:00Z")]}
            raise AssertionError("should never access a quarantined run artifact")
        with self.assertRaisesRegex(RuntimeError, "Nenhuma IPA candidata"):
            module.select_latest_successful_ipa_artifact(api)

    def test_main_invokes_dynamic_selector_only(self):
        with patch.object(module, "transfer_latest_successful_ipa",
                          return_value={"run_id": 999990001}) as new, \
             patch.object(module, "try_transfer_g1s_reader_trace",
                          side_effect=AssertionError("pinned old run")), \
             patch.object(module, "transfer_original_explicit",
                          side_effect=AssertionError("crashing original IPA")):
            self.assertEqual(module.main()["run_id"], 999990001)
            new.assert_called_once_with()

    def test_notebook_loads_current_branch_and_no_old_function_assertion(self):
        notebook = json.loads(
            (ROOT / "colab" / "Fairy2iOS_FairyTail2.ipynb").read_text())
        cells = [c for c in notebook["cells"] if c["cell_type"] == "code" and
                 "transfer_latest.main()" in "".join(c["source"])]
        self.assertEqual(len(cells), 1)
        src = "".join(cells[0]["source"])
        self.assertIn('subprocess.run(["git", "-C", str(REPO), "fetch"', src)
        self.assertIn('subprocess.run(["git", "-C", str(REPO), "reset"', src)
        self.assertIn('callable(transfer_latest.select_latest_successful_ipa_artifact)', src)
        self.assertNotIn("def try_transfer_g1t_header_rescue()", src)
        self.assertNotIn("45056917685", src)


if __name__ == "__main__":
    unittest.main()
