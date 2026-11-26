"""Test RAR fallback ordering and multipart guard without game files or apt."""
import importlib.util, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"colab"))
sys.path.insert(0,str(ROOT))
import archive_ingest as arc
class ExtractTests(unittest.TestCase):
    def test_multipart_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"base.part1.rar";p.write_bytes(b"Rar!"+b"0"*100)
            with patch.object(arc,"_install_rar_reader") as install:
                with self.assertRaisesRegex(RuntimeError,"base.part2.rar"):
                    arc.extract_packages(p,Path(tmp)/"out",".xci",1)
                install.assert_not_called()
    def test_existing_unrar_preferred_and_xci_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i in range(1,4): (root/f"base.part{i}.rar").write_bytes(b"Rar!"+b"0"*100)
            def run(command,directory,label):
                self.assertEqual(command[0],"/usr/bin/unrar")
                (directory/"base.xci").write_bytes(b"0"*256+b"HEAD")
                return 0,"OK"
            with patch.object(arc.shutil,"which",side_effect=lambda k:"/usr/bin/"+k if k in ("unrar","7z") else None), patch.object(arc,"_run_extractor",side_effect=run), patch.object(arc,"_install_rar_reader") as install:
                files=arc.extract_packages(root/"base.part1.rar",root/"out",".xci",1)
                self.assertEqual(len(files),1)
                install.assert_not_called()
