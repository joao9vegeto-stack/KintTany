"""Generic ELF PPU synthetic fixture and manifest boundary tests."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ppu_manifest_sanitize import sanitize
from make_synthetic_ppu import create_elf

class M2Tests(unittest.TestCase):
    def test_fixture_is_ppu(self):
        d=create_elf()
        self.assertEqual(d[:7],b"\x7fELF\x02\x02\x01")
        self.assertEqual(struct.unpack_from(">H",d,18)[0],21)
        self.assertEqual(struct.unpack_from(">Q",d,24)[0],0x20000)
    def test_fixture_opd(self):
        d=create_elf()
        self.assertEqual(struct.unpack_from(">IIII",d,0x2000),(0x10000,0x20080,0x10020,0x20080))
    def test_trim_large_bad_interval(self):
        funcs=[{"start":"0x6652d8","end":"0x81e468","toc":"0x83f2b0","opd":"0x8283e8"}]
        sec=[{"address":"0x6652d8","end":"0x6652fc"}]
        out,repairs=sanitize(funcs,sec)
        self.assertEqual(out[0]["end"],"0x6652fc")
        self.assertEqual(repairs[0]["invalid_tail_bytes_removed"],1806700)
        self.assertEqual(funcs[0]["end"],"0x81e468")
    def test_reject_outside_code(self):
        with self.assertRaises(ValueError):
            sanitize([{"start":"0x20000","end":"0x20008"}],[{"address":"0x10000","end":"0x10028"}])
    def test_reject_invalid_alignment(self):
        with self.assertRaises(ValueError):
            sanitize([{"start":"0x10002","end":"0x10008"}],[{"address":"0x10000","end":"0x10028"}])
