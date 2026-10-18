"""M7.45 exact PowerPC SRW frontier and iOS security-scoped folder gate."""
import unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class TestM745NativeSRW(unittest.TestCase):
 def test_native_owner_and_sha_gate(self):
  s=(R/"runtime/ppu_m745_native_srw.c").read_text()
  for x in ("0x7d290430","0x2f870000","0x7d694878","0x39430004",
            "0x91230000","0x419e0030","ar_m745_native_0052ba70",
            "ar_m712_exec_window","ar_read32","ar_write32"):
   self.assertIn(x,s)
  self.assertNotIn("ar_ppc_fallback_step",s)
  b=(R/"ios/ARLivePPUBridge.c").read_text()
  self.assertLess(b.index("ar_gowa2_offline_aot_install_sha256(digest"),
                  b.index("ar_m745_register_owner(d,len)"))
 def test_pipeline(self):
  self.assertIn("case 536:",(R/"runtime/ppu_m720_fallback.c").read_text())
  self.assertIn("runtime/ppu_m745_native_srw.c",(R/"tools/build_ios_probe_ipa.sh").read_text())
  w=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  self.assertIn("tests/host_m745_native_srw.c",w)
  self.assertIn("m745-native-arm64.o",w)
 def test_scope_before_directory_check(self):
  s=(R/"ios/ARGameFolderStore.m").read_text()
  self.assertLess(s.index("BOOL scoped=[folder startAccessingSecurityScopedResource]"),
                  s.index("fileExistsAtPath:folder.path"))
if __name__=="__main__":unittest.main()
