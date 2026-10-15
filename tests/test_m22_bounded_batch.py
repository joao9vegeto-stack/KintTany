"""No commercial inputs: only our own PPU synthetic fixture."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ppu_m22_bounded_batch import audit
from make_synthetic_ppu import create_elf

class BatchGateTests(unittest.TestCase):
    def test_two_complete_functions_and_rejected_partial(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"SYNTH.ELF"
            p.write_bytes(create_elf())
            rows=[
                {"start":"0x10000","end":"0x1000c"},
                {"start":"0x10020","end":"0x10028"},
                {"start":"0x1000c","end":"0x10020"}
            ]
            report=audit(p,rows,Path(td)/"generated")
            self.assertEqual(report["accepted_count"],2)
            self.assertEqual(report["rejected_count"],1)
            self.assertEqual(len(list((Path(td)/"generated").glob("ar_func_*.c"))),2)
            self.assertIn("declared range does not end in BLR",report["reasons"])
    def test_fails_closed_on_unsupported_branch(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"SYNTH.ELF"
            blob=bytearray(create_elf())
            blob[0x1000:0x1004]=(0x40000000).to_bytes(4,"big")
            p.write_bytes(blob)
            report=audit(p,[{"start":"0x10000","end":"0x1000c"}],Path(td)/"out")
            self.assertEqual(report["accepted_count"],0)
            self.assertEqual(report["rejected_count"],1)
