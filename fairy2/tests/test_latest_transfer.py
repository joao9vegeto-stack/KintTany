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

    def test_old_notebook_main_no_args_now_pins_diagnostic_run(self):
        # Already-open Colab cells call main() with no args; they must not
        # auto-fallback to the old KTGL-3250MiB IPA with inconsistent reports.
        with patch.object(module, "transfer_latest_successful_ipa",
                          return_value={"run_id": module.DIAGNOSTIC_RUN_ID}) as fn, \
             patch.object(module, "try_transfer_g1s_reader_trace",
                          side_effect=AssertionError("pinned old run")), \
             patch.object(module, "transfer_original_explicit",
                          side_effect=AssertionError("crashing original IPA")):
            self.assertEqual(module.main()["run_id"], module.DIAGNOSTIC_RUN_ID)
            fn.assert_called_once_with(diagnostic_run_id=module.DIAGNOSTIC_RUN_ID)

    def test_explicit_auto_selector_is_still_available_but_not_default(self):
        with patch.object(module, "transfer_latest_successful_ipa",
                          return_value={"run_id": 999990001}) as fn:
            self.assertEqual(module.main(diagnostic_run_id=None)["run_id"], 999990001)
            fn.assert_called_once_with()


    def test_exact_diagnostic_selector_rejects_stale_or_wrong_artifact(self):
        selected_run = run(module.DIAGNOSTIC_RUN_ID, "2026-11-23T00:17:01Z",
                           name=module.DIAGNOSTIC_WORKFLOW_NAME)
        selected_run["head_sha"] = module.DIAGNOSTIC_HEAD_SHA
        item = artifact(module.DIAGNOSTIC_RUN_ID,
                        name=module.DIAGNOSTIC_ARTIFACT_NAME,
                        size=1622005189, sha=module.DIAGNOSTIC_HEAD_SHA)
        item["id"] = module.DIAGNOSTIC_ARTIFACT_ID
        def api(path, params=None):
            if path == f"/actions/runs/{module.DIAGNOSTIC_RUN_ID}":
                return selected_run
            if path == f"/actions/runs/{module.DIAGNOSTIC_RUN_ID}/artifacts":
                return {"artifacts": [item]}
            raise AssertionError("Unexpected fallback " + path)
        actual, found, skipped = module.select_diagnostic_ipa_artifact(api)
        self.assertEqual(actual["id"], module.DIAGNOSTIC_RUN_ID)
        self.assertEqual(found["id"], module.DIAGNOSTIC_ARTIFACT_ID)
        self.assertEqual(skipped, [])
        with self.assertRaisesRegex(RuntimeError, "Só o run diagnóstico"):
            module.select_diagnostic_ipa_artifact(api, 45083487666)
        wrong = dict(item, name="Fairy2iOS-Diagnostic-INVALID")
        def bad_api(path, params=None):
            if path.endswith("/artifacts"):
                return {"artifacts": [wrong]}
            return selected_run
        with self.assertRaisesRegex(RuntimeError, "ausente, expirado"):
            module.select_diagnostic_ipa_artifact(bad_api)

    def test_diagnostic_main_does_not_use_automatic_fallback(self):
        with patch.object(module, "transfer_latest_successful_ipa",
                          return_value={"run_id": 45095021613,
                                        "diagnostic_only": True}) as fn:
            self.assertEqual(module.main(diagnostic_run_id=45095021613)["run_id"],
                             45095021613)
            fn.assert_called_once_with(diagnostic_run_id=45095021613)

    def test_notebook_loads_current_branch_and_no_old_function_assertion(self):
        notebook = json.loads(
            (ROOT / "colab" / "Fairy2iOS_FairyTail2.ipynb").read_text())
        cells = [c for c in notebook["cells"] if c["cell_type"] == "code" and
                 "transfer_latest.main(diagnostic_run_id=" in "".join(c["source"])]
        self.assertEqual(len(cells), 1)
        src = "".join(cells[0]["source"])
        self.assertIn('subprocess.run(["git", "-C", str(REPO), "fetch"', src)
        self.assertIn('subprocess.run(["git", "-C", str(REPO), "reset"', src)
        self.assertIn('callable(transfer_latest.select_diagnostic_ipa_artifact)', src)
        self.assertIn('RESULTADO_IPA = transfer_latest.main(diagnostic_run_id=45095021613)', src)
        self.assertIn('assert transfer_latest.DIAGNOSTIC_ARTIFACT_ID == 14783541081', src)
        self.assertIn('last_64_original_reads_on_failure', (ROOT / 'colab' / 'transfer_ipa.py').read_text())
        self.assertIn('assert transfer_latest.DIAGNOSTIC_HEAD_SHA == "3bf5b2c7dc978976fb7c7d2b569389fcd5b4f77a"', src)
        self.assertNotIn("def try_transfer_g1t_header_rescue()", src)
        self.assertNotIn("45056917685", src)

    def test_authentic_source_candidate_selector_exact_provenance(self):
        selected = run(module.AUTHENTIC_RUN_ID,"2026-11-23T02:30:00Z",
                       name=module.AUTHENTIC_WORKFLOW_NAME)
        selected["head_sha"]=module.AUTHENTIC_HEAD_SHA
        item = artifact(module.AUTHENTIC_RUN_ID,
                        name=module.AUTHENTIC_ARTIFACT_NAME,
                        size=1622016504, sha=module.AUTHENTIC_HEAD_SHA)
        item["id"]=module.AUTHENTIC_ARTIFACT_ID
        def api(path,params=None):
            if path==f"/actions/runs/{module.AUTHENTIC_RUN_ID}":
                return selected
            if path==f"/actions/runs/{module.AUTHENTIC_RUN_ID}/artifacts":
                return {"artifacts":[item]}
            raise AssertionError("No fallback to other IPA "+path)
        got,matched,skipped=module.select_authentic_source_candidate_artifact(api)
        self.assertEqual(got["id"],module.AUTHENTIC_RUN_ID)
        self.assertEqual(matched["id"],module.AUTHENTIC_ARTIFACT_ID)
        self.assertEqual(skipped,[])
        self.assertIn(45100431103,module.DEVICE_CRASH_RUNS)
        with self.assertRaisesRegex(RuntimeError,"só pode selecionar"):
            module.select_authentic_source_candidate_artifact(api,45100431103)
        with patch.object(module,"transfer_latest_successful_ipa",
                          return_value={"run_id":45177345329}) as fn:
            self.assertEqual(module.transfer_authentic_source_candidate()["run_id"],
                             45177345329)
            fn.assert_called_once_with(candidate_run_id=45177345329)

    def test_notebook_cell9_pins_repair_and_no_diagnostic_fallback(self):
        nb=json.loads((ROOT/"colab/Fairy2iOS_FairyTail2.ipynb").read_text())
        cells=[c for c in nb["cells"] if c["cell_type"]=="code"
             and "transfer_authentic_source_candidate(candidate_run_id=45100431103)" in
                 "".join(c["source"])]
        self.assertEqual(len(cells),1)
        src="".join(cells[0]["source"])
        self.assertIn("git\", \"-C\", str(REPO), \"reset",src)
        self.assertIn("AUTHENTIC_ARTIFACT_ID == 14784783270",src)
        self.assertIn("AUTHENTIC_HEAD_SHA == \"9298fe8eb3a26159538b4d456007f96b83c11ebe\"",src)
        self.assertIn("candidate_run_id=45100431103",src)
        self.assertIn('raise RuntimeError("NÃO EXECUTAR: run 45100431103',src)
        self.assertNotIn("main(diagnostic_run_id=",src)
        self.assertNotIn("result\":[\"diagnostic_only\"] is True",src)

    def test_cell10_pins_abi_corrected_candidate_and_retains_old_quarantine(self):
        nb=json.loads((ROOT/"colab/Fairy2iOS_FairyTail2.ipynb").read_text())
        cells=[c for c in nb["cells"] if c["cell_type"]=="code"
             and "transfer_authentic_source_candidate(candidate_run_id=45177345329)" in
                 "".join(c["source"])]
        self.assertEqual(len(cells),1)
        src="".join(cells[0]["source"])
        self.assertNotIn("raise RuntimeError",src)
        self.assertIn('subprocess.run(["git", "-C", str(REPO), "reset"',src)
        self.assertIn("AUTHENTIC_RUN_ID == 45177345329",src)
        self.assertIn("AUTHENTIC_ARTIFACT_ID == 14819613952",src)
        self.assertIn('AUTHENTIC_ARTIFACT_NAME == "Fairy2iOS-KTGL-ABI-and-Producer-Candidate-4"',src)
        self.assertIn('AUTHENTIC_HEAD_SHA == "b2aa579a22ca2e24889d0d6e1ab0b74ff3ee10ea"',src)
        self.assertIn("original_source_repair_candidate",src)
        self.assertNotIn("main(diagnostic_run_id=",src)
        self.assertIn(45100431103,module.DEVICE_CRASH_RUNS)
        self.assertTrue(callable(module.select_authentic_source_candidate_artifact))


if __name__ == "__main__":
    unittest.main()
