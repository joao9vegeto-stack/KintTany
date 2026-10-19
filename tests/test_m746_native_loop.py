"""M7.46: native owner hot loop over 69 authentic PowerPC64 words."""
import unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class M746HotLoop(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.native=(R/"runtime/ppu_m746_native_loop.c").read_text()
  cls.bridge=(R/"ios/ARLivePPUBridge.c").read_text()
  cls.build=(R/"tools/build_ios_probe_ipa.sh").read_text()
  cls.workflow=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  cls.plist=(R/"ios/Probe-Info.plist").read_text()
 def test_host_native_fused_69_ppc(self):
  for s in ("ar_m746_native_003ef6cc","ar_m746_native_003ef744",
            "ar_m746_native_003ef7ac","ar_m746_native_003ef7b4",
            "69u,UINT64_C(0x7a88b667fbb62b89)",
            "39u,UINT64_C(0x2a969db8283955ff)",
            "13u,UINT64_C(0x90f80017c002acdd)",
            "11u,UINT64_C(0x53cf015c5e88d5fc)",
            "ar_m712_exec_window","ar_read32",
            "ar_last_error()!=AR_OK","AR_PPC_LIMIT","c->ctr--"):
   self.assertIn(s,self.native)
  self.assertNotIn("ar_ppc_fallback_step",self.native)
 def test_original_sha_guard_before_loop_registration(self):
  self.assertIn("ar_m746_register_hotloop(d,len)",self.bridge)
  self.assertLess(self.bridge.index("ar_gowa2_offline_aot_install_sha256(digest"),
                  self.bridge.index("ar_m746_register_hotloop(d,len)"))
  self.assertLess(self.bridge.index("ar_m745_register_owner(d,len)"),
                  self.bridge.index("ar_m746_register_hotloop(d,len)"))
 def test_real_host_tests_and_apple_object_link(self):
  for s in ("runtime/ppu_m746_native_loop.c",
            "ios-probe/ppu_m746_native_loop.o",
            "AscensionRecompProbe-0.6.22-unsigned.ipa"):
   self.assertIn(s,self.build)
  for s in ("tests/host_m746_native_loop.c","m746-native-host.log",
            "m746-native-arm64.o","_ar_m746_register_hotloop"):
   self.assertIn(s,self.workflow)
  self.assertIn("<string>7641</string>",self.plist)
if __name__=="__main__":unittest.main()
