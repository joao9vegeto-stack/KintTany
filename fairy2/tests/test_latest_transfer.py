"""Guard rails: Colab cannot silently pick the crashing first Fairy Tail 2 IPA."""
from pathlib import Path
import sys
import importlib.util
import json
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"colab"))
file=ROOT/"colab/transfer_ipa.py"
spec=importlib.util.spec_from_file_location("fairy2_latest_transfer_regression",file)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class RepackTransferRegression(unittest.TestCase):
    def test_main_selects_repack_only(self):
        with patch.object(m,"try_transfer_host_repack",return_value=True) as latest, \
             patch.object(m,"transfer_original_explicit",side_effect=AssertionError("old IPA")):
            self.assertTrue(m.main())
            latest.assert_called_once_with()
    def test_main_never_falls_back_to_original(self):
        with patch.object(m,"try_transfer_host_repack",return_value=False), \
             patch.object(m,"transfer_original_explicit",side_effect=AssertionError("old IPA")):
            with self.assertRaisesRegex(RuntimeError,"Não existe repack"):
                m.main()
    def test_notebook_fetches_branch_in_same_transfer_cell(self):
        book=json.loads((ROOT/"colab/Fairy2iOS_FairyTail2.ipynb").read_text())
        cells=[x for x in book["cells"] if x["cell_type"]=="code"
               and "transfer_latest.main()" in "".join(x["source"])]
        self.assertEqual(len(cells),1)
        src="".join(cells[0]["source"])
        self.assertIn('subprocess.run(["git", "-C", str(REPO), "fetch"',src)
        self.assertIn('subprocess.run(["git", "-C", str(REPO), "reset"',src)
        self.assertIn('spec_from_file_location("fairy2_latest_repack_transfer"',src)
        self.assertIn("base 44965722551 BLOQUEADA",src)
    def test_no_implicit_original_in_main_body(self):
        src=file.read_text()
        main=src.split("def main():",1)[1]
        self.assertIn("try_transfer_host_repack()",main)
        self.assertNotIn("transfer_original_explicit()",main)

if __name__=="__main__":
    unittest.main()
