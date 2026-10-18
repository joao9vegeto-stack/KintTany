"""M7.53 VMX family is reusable by CFG lifter, fallback and owner AOT."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from ppu_cfg_lifter import lift,Unsupported
class VMXFamily(unittest.TestCase):
 def test_four_word_vector_family_lifts_generically(self):
  source,h=lift([0x10a0190a,0x1065f8ef,0x1063296e,
                 0x1063f12e,0x4e800020],0x3b062c)
  self.assertEqual(h.get('vrefp'),1)
  self.assertEqual(h.get('vnmsubfp'),1)
  self.assertEqual(h.get('vmaddfp'),2)
  for x in ("ar_vmx_vrefp(c,5,3)","ar_vmx_vmaddfp(c,3,5,31,3,1)",
            "ar_vmx_vmaddfp(c,3,3,5,5,0)",
            "ar_vmx_vmaddfp(c,3,3,30,4,0)"):
   self.assertIn(x,source)
  self.assertIn('#include "ppu_vmx_cell.h"',source)
 def test_invalid_reserved_vrefp_not_lifted(self):
  with self.assertRaises(Unsupported):
   lift([0x10a1190a,0x4e800020],0x3b062c)
 def test_generic_path_connected(self):
  bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
  fallback=(ROOT/"runtime/ppu_m720_fallback.c").read_text()
  aot=(ROOT/"runtime/ppu_m753_native_vectorfp.c").read_text()
  vmx=(ROOT/"runtime/ppu_vmx_cell.h").read_text()
  self.assertIn("ar_m753_register_vectorfp(d,len)",bridge)
  self.assertIn("ar_vmx_vrefp(c,d,b)",fallback)
  self.assertIn("ar_vmx_vmaddfp(c,d,a,b,vc,",fallback)
  self.assertIn("fmaf(",vmx)
  self.assertIn("ar_m712_exec_window",aot)
  self.assertIn("0x003b063c",aot)
  self.assertIn("0x10a0190a",aot)
  self.assertIn("0x1063f12e",aot)
 def test_ci_real_ios_link(self):
  sh=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
  flow=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
  self.assertIn("ppu_m753_native_vectorfp.o",sh)
  self.assertIn("_ar_m753_register_vectorfp",sh)
  self.assertIn("host_m753_vectorfp.c",flow)
  self.assertIn("m753-vectorfp-host.log",flow)
if __name__=="__main__":unittest.main()
