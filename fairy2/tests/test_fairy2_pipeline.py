#!/usr/bin/env python3
"""Static Fairy2iOS game identity, DLC packing and notebook regression checks."""
from __future__ import annotations
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "fairy2"
TITLE = "0100B9801F872000"

class Fairy2PipelineTests(unittest.TestCase):
    def test_notebook_compiles_and_has_eight_stages(self):
        nb = json.loads((GAME / "colab/Fairy2iOS_FairyTail2.ipynb").read_text())
        code = ["".join(cell["source"]) for cell in nb["cells"] if cell["cell_type"] == "code"]
        self.assertEqual(nb["nbformat"], 4)
        self.assertEqual(len(code), 8)
        for i, source in enumerate(code):
            ast.parse("\n".join(line for line in source.splitlines()
                                if not line.lstrip().startswith(("!", "%"))),
                      filename=f"colab-cell-{i}")
        self.assertIn("BASE_RAR_URL", code[2])
        self.assertIn("UPDATE_RAR_URL", code[2])
        self.assertIn("DLC_RAR_URL", code[2])
        self.assertIn("archive_ingest.ingest(", code[2])
        self.assertIn("run_colab.prepare(", code[4])
        self.assertIn("run_colab.dispatch(", code[6])
        self.assertIn("transfer_ipa.main()", code[7])
        self.assertIn("== 18", code[5])
        self.assertIn("== 16", code[5])
        self.assertIn(TITLE, "".join(code))

    def test_isolated_actions(self):
        flow = (ROOT / ".github/workflows/fairy2.yml").read_text()
        self.assertIn("branches: [Fairy2iOS]", flow)
        self.assertIn("paths: ['fairy2/handoff.json']", flow)
        self.assertIn("runs-on: xcode-27", flow)
        self.assertIn("cancel-in-progress: true", flow)
        self.assertIn("fairy2/scripts/build_shared.py", flow)
        self.assertNotIn("biotant/scripts/build_shared.py", flow)
        self.assertNotIn("download_token=", flow)
        self.assertNotIn("44880915730", (GAME / "scripts/repack_ipa.py").read_text())

    def test_full_18_nsp_dlc_provenance(self):
        source = (GAME / "colab/source_archive.py").read_text()
        ingest = (GAME / "colab/archive_ingest.py").read_text()
        linux = (GAME / "colab/prepare_linux.py").read_text()
        handoff = (GAME / "colab/run_colab.py").read_text()
        actions = (GAME / "scripts/prepare_actions.py").read_text()
        self.assertIn("DLC_COUNT = 16", source)
        self.assertIn("expected_count=16", ingest)
        self.assertIn("len(files) == 18", linux)
        self.assertIn('len(family["dlc"]) == 16', linux)
        self.assertIn('"input_dlc_count": 16', linux)
        self.assertIn("aoc_records.append(upload_drive_file", handoff)
        self.assertIn('download_drive_file(api, entry, work / "aoc" / name)', actions)
        self.assertIn('GAME_FOLDER_ID = "1QNa5LUK7Es-evrRIAjtUVzrhGUhENn5t"', source)
        for content in (source, ingest, linux, handoff, actions):
            self.assertNotIn("download_token=", content)

if __name__ == "__main__":
    unittest.main()
