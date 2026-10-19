"""Regression: authentic M7.62 inventory stores PC as JSON integers, older exports use hex."""
import sys,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tools'))
import m763_expand

class SnapshotPCEncoding(unittest.TestCase):
 def test_integer_and_hex_are_equivalent(self):
  for pc in (0x002c53b0,0x00539378,0x00010410):
   self.assertEqual(m763_expand.parse_pc(pc),pc)
   self.assertEqual(m763_expand.parse_pc('0x%08X'%pc),pc)
 def test_reject_bad_pc(self):
  for pc in (-1,0x100000000,0x539379,True,{},'oops'):
   with self.assertRaises(ValueError):m763_expand.parse_pc(pc)
if __name__=='__main__':unittest.main()
