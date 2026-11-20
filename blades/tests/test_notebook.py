#!/usr/bin/env python3
"""Regression checks for the *real uploaded Dante* 13-cell BladesTime notebook."""
from __future__ import annotations
import ast
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DanteNotebookParity(unittest.TestCase):
    def test_original_13_cell_structure_and_order(self):
        nb = json.loads((ROOT / "blades/colab/BladesTime.ipynb").read_text())
        self.assertEqual(nb["nbformat"], 4)
        self.assertEqual(len(nb["cells"]), 13)
        intro = "".join(nb["cells"][0]["source"])
        self.assertIn("3 (autenticar Drive)", intro)
        self.assertIn("13 (disparar um Actions)", intro)
        self.assertIn("célula 2 de transferência", intro)
        self.assertEqual([i for i,c in enumerate(nb["cells"]) if c["cell_type"] == "code"],
                         [1,2,4,6,8,10,12])
        for i,c in enumerate(nb["cells"]):
            body = "".join(c["source"])
            if c["cell_type"] == "code":
                python = "\n".join(line for line in body.splitlines()
                                   if not line.startswith("!") and not line.startswith("%"))
                ast.parse(python)
            for old in ("Dante2iOS-repo", "dmc2/handoff", "Dante2iOS-DMC2.ipa",
                        "01007CF00D5BA000"):
                self.assertNotIn(old, body, (i, old))

    def test_transfer_is_original_cell_one_and_game_specific(self):
        nb = json.loads((ROOT / "blades/colab/BladesTime.ipynb").read_text())
        cell = "".join(nb["cells"][1]["source"])
        self.assertIn('BRANCH = "BladesTime"', cell)
        self.assertIn('IPA_NAME = "BladesTime-BoTime.ipa"', cell)
        self.assertIn('".github/workflows/bladestime.yml"', cell)
        self.assertIn('startswith("BladesTime-BoTime-")', cell)
        self.assertIn('botime_folders =', cell)
        self.assertIn('EXPECTED_ARTIFACT_SHA256', cell)
        self.assertIn('archive.testzip()', cell)

    def test_nxnative_recovery_update_and_handoff(self):
        nb = json.loads((ROOT / "blades/colab/BladesTime.ipynb").read_text())
        code = lambda i: "".join(nb["cells"][i]["source"])
        self.assertIn('auth.authenticate_user()', code(2))
        self.assertIn('--branch BladesTime', code(4))
        self.assertIn('run_colab.recover(', code(6))
        self.assertIn('run_colab.prepare(', code(8))
        self.assertIn('ensure_linux_native_extractor', code(8))
        self.assertIn('update_content_version', code(10))
        self.assertIn('input_package_count"] == 2', code(10))
        self.assertIn('input_update_count"] == 1', code(10))
        self.assertIn('blades/colab/run_colab.py dispatch', code(12))


if __name__ == "__main__":
    unittest.main()
