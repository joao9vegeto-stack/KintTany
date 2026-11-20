#!/usr/bin/env python3
"""Regression checks for the user-facing one-cell BladesTime/Dante-style Colab flow."""
import ast
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class NotebookTests(unittest.TestCase):
    def test_one_cell_with_all_pipeline_modes(self):
        notebook = json.loads((ROOT / "blades/colab/BladesTime.ipynb").read_text())
        self.assertEqual(notebook["nbformat"], 4)
        code = [c for c in notebook["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(code), 1, "Only one executable cell is allowed for iPhone use")
        cell = "".join(code[0]["source"])
        ast.parse(cell)
        self.assertIn('# @param ["PREPARAR + ACTIONS", "RECUPERAR UPLOAD + ACTIONS", "TRANSFERIR IPA PARA DRIVE"]', cell)
        self.assertIn("auth.authenticate_user()", cell)
        self.assertIn("getpass.getpass", cell)
        self.assertIn('"--drive-folder-id", parent_id', cell)
        self.assertIn('executar(script, "prepare"', cell)
        self.assertIn('executar(script, "recover"', cell)
        self.assertIn('executar(script, "dispatch"', cell)
        self.assertIn('blades" / "colab" / "transfer_ipa.py"', cell)
        self.assertIn("BLADES_GITHUB_TOKEN", cell)
        self.assertNotIn("ghp_", cell)
        self.assertNotIn("github_pat_", cell)

    def test_dispatch_prefers_secure_notebook_prompt(self):
        source = (ROOT / "blades/colab/run_colab.py").read_text()
        ast.parse(source)
        self.assertIn('os.environ.get("BLADES_GITHUB_TOKEN", "")', source)
        self.assertIn("d.get(\"project\") != \"BladesTime\"", source)
        self.assertNotIn("dmc2/handoff.json", source)

    def test_transfer_ipa_hashes_and_identity(self):
        path = ROOT / "blades/colab/transfer_ipa.py"
        spec = importlib.util.spec_from_file_location("bladestime_transfer", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.BRANCH, "BladesTime")
        self.assertEqual(module.TITLE_ID, "0100CFA00CC74000")
        self.assertEqual(module.WORKFLOW, "bladestime.yml")
        self.assertEqual(module.WORKERS, 6)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sample.ipa"
            p.write_bytes(b"test-case-ipa" * 17)
            sha, md5 = module.hashes(p)
            self.assertEqual(sha, hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(md5, hashlib.md5(p.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
