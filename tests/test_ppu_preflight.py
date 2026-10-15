"""Synthetic ELF tests only; no game data enters GitHub Actions."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "tools"))
from ppu_preflight import analyze,PPUError

def fixture():
    d=bytearray(0x800)
    struct.pack_into(">16sHHIQQQIHHHHHH",d,0,b"\x7fELF\x02\x02\x01\x66"+bytes(8),2,21,1,0x10080,64,0x200,0,64,56,1,64,3,2)
    struct.pack_into(">IIQQQQQQ",d,64,1,5,0x400,0x10000,0,0x300,0x300,16)
    names=b"\x00.opd\x00.shstrtab\x00"
    d[0x360:0x360+len(names)]=names
    struct.pack_into(">IIQQQQIIQQ",d,0x200+64,1,1,2,0x10080,0x480,0x18,0,0,8,0)
    struct.pack_into(">IIQQQQIIQQ",d,0x200+128,6,3,0,0,0x360,len(names),0,0,1,0)
    struct.pack_into(">II",d,0x480,0x10020,0x10180)
    struct.pack_into(">II",d,0x488,0x10040,0x10180)
    return d

class PPUTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"TEST.ELF"
    def tearDown(self):self.temp.cleanup()
    def test_opd_entry_and_functions(self):
        self.path.write_bytes(fixture())
        r=analyze(self.path)
        self.assertEqual(r["opd_unique_functions"],2)
        self.assertEqual(r["ppu_entry_code"],"0x10020")
        self.assertEqual(r["ppu_entry_toc"],"0x10180")
        self.assertEqual(r["opd_section"]["name"],".opd")
        self.assertEqual(r["imports_total"],0)
    def test_reject_corrupt(self):
        self.path.write_bytes(bytes(20))
        with self.assertRaises(PPUError):analyze(self.path)
    def test_reject_wrong_architecture(self):
        d=fixture();struct.pack_into(">H",d,18,62);self.path.write_bytes(d)
        with self.assertRaises(PPUError):analyze(self.path)
