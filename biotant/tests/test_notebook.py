#!/usr/bin/env python3
"""Offline notebook and workflow identity tests, no game data or credentials."""
from __future__ import annotations
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "biotant" / "colab" / "BioiOSMutant_Biomutant.ipynb"
TITLE = "01004BA017CD6000"


class BiomutantNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.code = ["".join(c["source"]) for c in cls.notebook["cells"]
                    if c["cell_type"] == "code"]
        cls.all_text = "\n".join("".join(c["source"]) for c in cls.notebook["cells"])

    def test_order_and_live_python_syntax(self):
        self.assertEqual(self.notebook["nbformat"], 4)
        self.assertEqual(len(self.code), 8)
        for index, source in enumerate(self.code):
            python_source = "\n".join(line for line in source.splitlines()
                                       if not line.lstrip().startswith(("!", "%")))
            ast.parse(python_source, filename=f"cell-{index}")
        self.assertIn("archive_ingest.ingest(", self.code[2])
        self.assertIn("run_colab.prepare(", self.code[4])
        self.assertIn("run_colab.dispatch(", self.code[6])
        self.assertIn("transfer_ipa.main()", self.code[7])

    def test_correct_game_and_input_links(self):
        self.assertIn(TITLE, self.all_text)
        self.assertIn("BioiOSMutant", self.all_text)
        self.assertIn("BIOTANT_FOLDER_ID", self.code[0])
        self.assertIn("Biomutant_(NSP)(eShop).rar", self.code[2])
        self.assertIn("BOIMUTNT-(USA)-NSwTcH-NSP-Update102-Ziperto.rar", self.code[2])
        self.assertNotIn("0100CFA00CC74000", self.all_text)
        self.assertNotIn("v262144", self.all_text)

    def test_workflow_only_handoff(self):
        workflow = (ROOT / ".github" / "workflows" / "biomutant.yml").read_text()
        self.assertIn("branches: [BioiOSMutant]", workflow)
        self.assertIn("paths: ['biotant/handoff.json']", workflow)
        self.assertIn("runs-on: xcode-27", workflow)
        self.assertIn("biotant/scripts/build_shared.py", workflow)
        self.assertNotIn("extract_dagor_shdump", workflow)
        self.assertNotIn("v262144", workflow)

    def test_rar_ingestion_and_drive_paths(self):
        src = (ROOT / "biotant" / "colab" / "archive_ingest.py").read_text()
        self.assertIn("base.nsp", src)
        self.assertIn("update.nsp", src)
        self.assertIn("upload_checked", src)
        self.assertIn("archive.unlink(missing_ok=True)", src)
        self.assertIn("md5Checksum", src)
        source = (ROOT / "biotant" / "colab" / "source_archive.py").read_text()
        self.assertIn("01004BA017CD6000", source)
        self.assertIn("1yrL87jYVf08FGB2eWV5CY0jBp2OTHYAs", source)


if __name__ == "__main__":
    unittest.main()
