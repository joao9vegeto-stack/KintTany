import sys,struct,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from make_synthetic_ppu import create_elf
from recover_ppu_calls import scan_elf,PPUFormatError
class RecoverCalls(unittest.TestCase):
 def test_direct_branch_with_prologue(self):
  d=bytearray(create_elf())
  struct.pack_into('>I',d,0x1000+0x20,0xf821ff91)
  r=scan_elf(bytes(d),{0x10000})
  self.assertEqual(r['recovered_not_in_opd'],1)
  self.assertEqual(r['candidates'][0]['entry'],'0x10020')
 def test_no_false_positive_for_no_prologue(self):
  r=scan_elf(create_elf(),{0x10000})
  self.assertEqual(r['recovered_not_in_opd'],0)
 def test_reject_not_elf(self):
  with self.assertRaises(PPUFormatError):scan_elf(b'hello',{0x10000})
