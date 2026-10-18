"""M7.54 regression: generic PPC FCMPU/FCMPO and exact signed owner branch."""
from pathlib import Path
import sys,unittest
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"tools"))
from ppu_cfg_lifter import lift,Unsupported
class PPCCompare(unittest.TestCase):
 def test_generic_compare_is_aot_lifted(self):
  for code,name in [(0xfc01f800,"fcmpu"),(0xfc01f840,"fcmpo")]:
   src,h=lift([code,0x4e800020],0x3b064c)
   self.assertEqual(h[name],1)
   self.assertIn("ar_fp_compare(c,0,1,31,",src)
   self.assertIn('#include "ppu_fp_scalar.h"',src)
 def test_reserved_field_fails(self):
  with self.assertRaises(Unsupported):
   lift([0xfc21f800,0x4e800020],0x3b064c)
 def test_native_and_fallback_connected(self):
  source=(R/"runtime/ppu_m754_native_fcmp.c").read_text()
  bridge=(R/"ios/ARLivePPUBridge.c").read_text()
  fp=(R/"runtime/ppu_fp_scalar.h").read_text()
  fb=(R/"runtime/ppu_m720_fallback.c").read_text()
  self.assertIn("ar_m754_register_fcmp_branch(d,len)",bridge)
  self.assertIn("0xfc01f800",source)
  self.assertIn("0x41810018",source)
  self.assertIn("0x003b0668",source)
  self.assertIn("0x003b0654",source)
  self.assertIn("ar_fp_compare(c,bf,a,b,xo==32u)",fb)
  self.assertIn("c->fpscr=(c->fpscr",fp)
 def test_build_and_evidence(self):
  sh=(R/"tools/build_ios_probe_ipa.sh").read_text()
  wf=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  self.assertIn("ppu_m754_native_fcmp.o",sh)
  self.assertIn("_ar_m754_register_fcmp_branch",sh)
  self.assertIn("tests/host_m754_fcmp.c",wf)
if __name__=="__main__":unittest.main()
