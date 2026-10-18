"""M7.44: native C-AOT guest 0x003F2860 CROR+BC with original ELF gate."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class TestM744NativeCROR(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
  cls.build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
  cls.native=(ROOT/"runtime/ppu_m744_native_cror.c").read_text()
  cls.workflow=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
 def test_apple_aot_not_fallback_and_guest_state(self):
  for token in ("ar_m744_native_003f2860", "c->cr=(old_cr&~", "c->cia=cond?",
                "return AR_TAIL", "ar_m744_register_owner",
                "words[0]!=AR_M744_CROR", "words[1]!=AR_M744_BEQ",
                "ar_read32(AR_M744_PC", "ar_last_error()!=AR_OK"):
   self.assertIn(token,self.native)
  self.assertNotIn("ar_ppc_fallback_step",self.native)
  self.assertNotIn("rpcs3",self.native.lower())
 def test_ordered_after_sha_and_offline_aot(self):
  self.assertIn("ar_m744_register_owner(d,len)",self.bridge)
  self.assertLess(self.bridge.index("ar_private_aot_install_sha256("),
                  self.bridge.index("ar_m744_register_owner(d,len)"))
  self.assertLess(self.bridge.index("ar_gowa2_offline_aot_install_sha256(digest"),
                  self.bridge.index("ar_m744_register_owner(d,len)"))
 def test_link_and_real_host_tests(self):
  self.assertIn("runtime/ppu_m744_native_cror.c",self.build)
  self.assertIn("ios-probe/ppu_m744_native_cror.o",self.build)
  self.assertIn("tests/host_m744_native_cror.c",self.workflow)
  self.assertIn("m744-native-host.log",self.workflow)
  self.assertIn("m744-native-arm64.o",self.workflow)
  self.assertIn("M7.44",self.workflow)
if __name__=="__main__":
 unittest.main()
