"""AOT-only owner block and independent ELF-vs-memory diagnostic contracts."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class TestM756(unittest.TestCase):
 def test_both_windows_and_no_interpreter(self):
  s=(R/"runtime/ppu_m756_native_divloop.c").read_text()
  for w in ("0x30c90004","0x7cc63b96","0x7cc639d6",
            "0x7cc64810","0x30c60004","0x2c060000",
            "0x41820008","0x003c4fe4","0x003c4fe0"):
   self.assertIn(w,s)
  self.assertIn("ar_m712_exec_window",s)
  self.assertIn("ar_read32(pc)",s)
  self.assertNotIn("ar_ppc_fallback_step",s)
  self.assertNotIn("ar_ppc_fallback_attach",s)
 def test_capture_real_ram_before_bridge_shutdown(self):
  b=(R/"ios/ARLivePPUBridge.c").read_text()
  diag=(R/"runtime/ppu_m756_stop_evidence.c").read_text()
  ui=(R/"ios/ARProbeApp.m").read_text()
  self.assertLess(b.index("ar_m756_capture_stop(d,len,out[7]"),b.index("ar_bridge_shutdown();\n return 0;"))
  self.assertIn("ar_vm_read_bytes(pc,out->guest_bytes,n)",diag)
  self.assertIn("file_offset=at",diag)
  self.assertIn("ar_m756_last_stop_evidence",ui)
  self.assertIn("ar_m756_last_origin_evidence",ui)
  self.assertIn("ar_m756_capture_stop(d,len,UINT32_C(0x003c4fc4)",b)
  self.assertIn("ELF versus RAM guest",ui)
  self.assertNotIn('@"opcode":@(measured.fallback_unsupported_word)',ui)
 def test_ci_and_final_binary(self):
  b=(R/"tools/build_ios_probe_ipa.sh").read_text()
  wf=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  for token in ("ppu_m756_native_divloop.o","ppu_m756_stop_evidence.o",
                "_ar_m756_register_divloop","_ar_m756_capture_stop"):
   self.assertIn(token,b)
  for t in ("host_m756_divloop.c","host_m756_stop_evidence.c",
            "m756-divloop-host.log","m756-stop-evidence-host.log"):
   self.assertIn(t,wf)
if __name__=="__main__":unittest.main()
