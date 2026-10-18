"""Generic VMX VADDFP instruction now supported by the offline PPC->C lifter.
This is NOT evidence an AOT owner module invokes it on the iPhone."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from ppu_cfg_lifter import lift
class Vaddfp(unittest.TestCase):
 def test_real_owner_frontier_is_liftable(self):
  source, hist=lift([0x1108380a,0x4e800020],0x003b085c)
  self.assertEqual(hist.get('vaddfp'),1)
  self.assertIn('ar_vmx_vaddfp(c,8,8,7)',source)
  self.assertIn('#include "ppu_vmx_cell.h"',source)
 def test_vaddfp_only_supports_exact_xo(self):
  s=(ROOT/"runtime/ppu_vmx_cell.h").read_text()
  self.assertIn("static inline int ar_vmx_vaddfp",s)
  self.assertIn("fegetround()!=FE_TONEAREST",s)
  self.assertIn("ar_vmx_fp_result(added",s)
  self.assertIn("if(xo==10u)",(ROOT/"runtime/ppu_m720_fallback.c").read_text())
if __name__=='__main__':unittest.main()
