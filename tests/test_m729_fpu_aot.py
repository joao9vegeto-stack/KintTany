"""M7.29 native AOT PPC64 FPU lifter regressions; synthetic words only."""
import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ppu_cfg_lifter import lift,Unsupported
BLR=0x4e800020
def d(o,t,a,i):return (o<<26)|(t<<21)|(a<<16)|(i&65535)
def f(t,a,b,x,rc=0):return (63<<26)|(t<<21)|(a<<16)|(b<<11)|(x<<1)|rc
class TestM729FPU(unittest.TestCase):
 def test_exact_fcfid_raw_bits_codegen(self):
  src,h=lift([d(50,0,1,128),f(13,0,0,846),BLR],0x10000)
  self.assertEqual(h['fp_load'],1);self.assertEqual(h['fcfid'],1)
  self.assertIn('ar_fp_fcfid',src)
  self.assertNotIn('ar_ppc_fallback_step',src)
 def test_literal_complete_fp_sequence(self):
  x=[d(50,0,1,128),f(13,0,0,846),d(48,0,2,0),
     f(0,13,0,18),d(54,0,11,0),BLR]
  src,h=lift(x,0x10000)
  for name,n in [('fp_load',2),('fp_store',1),('fcfid',1),('fdiv',1)]:
   self.assertEqual(h[name],n)
  self.assertIn('ar_fp_fdiv',src)
  self.assertIn('ar_fp_store',src)
 def test_signed_dform_displacement(self):
  src,h=lift([d(48,0,2,-25436),BLR],0x10000)
  self.assertIn('-25436',src);self.assertEqual(h['fp_load'],1)
 def test_guest_register_abi_shared_by_compilers(self):
  src,h=lift([d(50,13,1,128),d(54,13,11,0),BLR],0x10000)
  self.assertIn('ppu_fp_scalar.h',src)
  self.assertIn('ar_fp_load(c,13',src)
  self.assertIn('ar_fp_store(c,13',src)
 def test_reserved_encoding_fail_closed(self):
  for word in [f(13,1,0,846),f(0,13,0,18,1),f(0,0,0,99)]:
   with self.subTest(word=hex(word)):
    with self.assertRaises(Unsupported):lift([word,BLR],0x10000)
if __name__=='__main__':unittest.main()
