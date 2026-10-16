"""M7.4 structural tests: no external commercial game or Xcode."""
import json
import tempfile
import unittest
from pathlib import Path
from sys import path
path.insert(0,str(Path(__file__).resolve().parents[1] / "tools"))
from ppu_aot_build import build
from m74_make_fixture import create

class TestPrivateAOT(unittest.TestCase):
    def test_synthetic_module_and_digest(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);elf=d/"fixture.elf";fn=d/"functions.json"
            create(elf,fn)
            out=d/"private"
            report=build(elf,fn,out,0x10000)
            self.assertEqual(report["generated_functions"],2)
            self.assertEqual(report["rejected_functions"],0)
            src=(out/"ascension_private_aot.c").read_text()
            self.assertIn("ar_private_aot_install_sha256",src)
            self.assertIn("ar_game_ppu_00010000",src)
            self.assertIn("ar_game_ppu_00010010",src)
            self.assertNotIn("ar_m71_signed_ppu_interpret",src)
            self.assertEqual(len(report["source_sha256"]),64)
            with self.assertRaises(ValueError):
                build(elf,fn,d/"invalid-entry",0x99999)
            tampered=bytearray(elf.read_bytes());tampered[-1]^=1
            elf.write_bytes(tampered)
            report2=build(elf,fn,d/"tampered",0x10000)
            self.assertNotEqual(report2["source_sha256"],report["source_sha256"])
    def test_duplicate_and_unsupported_are_visible(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);elf=d/"fixture.elf";fn=d/"functions.json"
            create(elf,fn)
            rows=json.loads(fn.read_text());rows.append(rows[0])
            fn.write_text(json.dumps(rows))
            with self.assertRaises(ValueError):
                build(elf,fn,d/"bad",0x10000)
            fn.write_text(json.dumps([{"start":"0x10000","end":"0x1000c"}]))
            with self.assertRaises(ValueError):
                build(elf,fn,d/"no-functions",0x10000)
