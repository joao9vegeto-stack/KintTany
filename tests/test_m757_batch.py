"""M7.57: production AOT continuation spans and artifact evidence contracts."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class M757(unittest.TestCase):
 def test_original_authenticated_entries_and_branches(self):
  s=(ROOT/"runtime/ppu_m757_native_batch.c").read_text()
  for word in ("0x311f0004","0x7d083b96","0x7d0839d6",
               "0x7f88f810","0x339c0004","0x2c1c0000",
               "0x41820008","0x7f9c3810","0x7fbc2014",
               "0x281c0020","0x57de113a","0x7bbd0020",
               "0x41800048","0x7c9df010","0x28040010","0x418000b0"):
   self.assertIn(word,s)
  self.assertIn("ar_m712_exec_window",s)
  self.assertIn("ar_read32(at)",s)
  self.assertIn("0x003c5084",s)
  self.assertIn("0x003c50c8",s)
  self.assertIn("0x003c5180",s)
  self.assertIn("0x003c50d4",s)
  self.assertIn("rc==AR_DUPLICATE ? AR_OK : rc",s)
  self.assertIn("ar_m757_register_owner(fake,sizeof(fake))!=AR_OK", (ROOT/"tests/host_m757_native_batch.c").read_text())
  self.assertNotIn("ar_ppc_fallback_step",s)
 def test_runtime_uses_aot_only(self):
  bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
  build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
  self.assertIn("ar_m757_register_owner(d,len)",bridge)
  self.assertIn("ppu_m757_native_batch.o",build)
  self.assertIn("_ar_m757_native_003c5050",build)
  self.assertIn("_ar_m757_native_003c50c8",build)
  self.assertIn("ASCENSION_NATIVE_ONLY=1",build)
  self.assertNotIn('    ios-probe/ppu_m720_fallback.o \\',build)
 def test_ui_physically_sourced_not_fake_FS(self):
  ui=(ROOT/"ios/ARProbeApp.m").read_text()
  self.assertIn("App=%@",ui)
  self.assertIn("M7.61.3 (teste físico",ui)
  self.assertIn("ELF versus RAM guest",ui)
  self.assertIn("cellFsRead com bytes positivos",ui)
  self.assertIn("ownerStop.guest_word",ui)
  self.assertNotIn('@"opcode":@(measured.fallback_unsupported_word)',ui)
 def test_ci_link(self):
  flow=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
  self.assertIn("host_m757_native_batch.c",flow)
  self.assertIn("m757-native-host.log",flow)
  self.assertIn("ppu_m757_native_batch",flow)
if __name__=="__main__":unittest.main()
