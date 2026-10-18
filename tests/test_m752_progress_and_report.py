"""M7.52 actual frontier; file metadata must never masquerade as guest reads."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class M752(unittest.TestCase):
 def test_native_frontier_and_fallback(self):
  native=(R/"runtime/ppu_m752_vsldoi.c").read_text()
  generic=(R/"runtime/ppu_vmx_cell.h").read_text()
  interp=(R/"runtime/ppu_m720_fallback.c").read_text()
  bridge=(R/"ios/ARLivePPUBridge.c").read_text()
  for item in ("0x003b0608","0x105ff82c","0x003b060c",
               "ar_m712_exec_window","ar_read32","ar_register"):
   self.assertIn(item,native)
  self.assertIn("ar_vmx_vsldoi",generic)
  self.assertIn("if((xo&0x43fu)==44u)",interp)
  self.assertLess(bridge.index("ar_m751_register_vsubfp(d,len)"),
                  bridge.index("ar_m752_register_vsldoi(d,len)"))
 def test_report_uses_correct_slots_and_actual_build(self):
  ui=(R/"ios/ARProbeApp.m").read_text()
  self.assertIn('App=M7.57',ui)
  self.assertIn('last,origin,elf,native,',ui)
  self.assertIn('self.m750HostObservation?:@"não comprovado",',ui)
  self.assertIn('fsOpen,fsRead];',ui)
  self.assertIn('M7.56 (teste físico',ui)
  self.assertIn('HOST Files separado',ui)
  self.assertIn('self.m750HostObservation?:@"não comprovado",\n     fsOpen,fsRead];',ui)
  self.assertIn('fs_open_calls',ui)
  self.assertIn('fs_read_calls',ui)
 def test_production_link_and_ci_gate(self):
  s=(R/"tools/build_ios_probe_ipa.sh").read_text()
  w=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  for item in ("ppu_m752_vsldoi.o","_ar_m752_register_vsldoi",
               "ppu_guest_fs.o"):
   self.assertIn(item,s)
  for item in ("host_m752_vsldoi.c","m752-vsldoi-host.log",
               "_ar_m752_register_vsldoi"):
   self.assertIn(item,w)
if __name__=="__main__":unittest.main()
