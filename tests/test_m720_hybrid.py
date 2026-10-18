"""M7.20 hybrid execution architecture: AOT first, experimental PPC fallback.

Never uses game ELF, source secrets, or invented RSX/gameplay status.
"""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class HybridM720Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.header=(ROOT/"runtime/ppu_bridge.h").read_text()
  cls.bridge=(ROOT/"runtime/ppu_bridge.c").read_text()
  cls.fallback=(ROOT/"runtime/ppu_m720_fallback.c").read_text()
  cls.ios=(ROOT/"ios/ARLivePPUBridge.c").read_text()
  cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()
  cls.build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()

 def test_guest_aot_remains_native_and_fallback_counter_separate(self):
  c=self.bridge
  self.assertLess(c.index("ar_ppu_fn fn=lookup(pc,&found_index);"),
                  c.index("const int step=fb_eval("))
  self.assertIn("if(fb_elf && fb_eval)",c)
  self.assertIn("trace_total++;",c)
  self.assertIn("fb_steps++;",c)
  self.assertIn("AR_PPC_UNSUPPORTED",c)
  self.assertIn("AR_PPC_LIMIT",c)
  self.assertIn("fallback_steps",self.header)
  self.assertIn("fb_elf=0;fb_eval=0;",c)
  self.assertNotIn("ar_register(",self.fallback)

 def test_sha_guard_before_fallback_and_isa_failure_closed(self):
  i=self.ios
  self.assertLess(i.index("ar_private_aot_install_sha256(digest,sizeof(digest))"),
                  i.index("ar_ppc_fallback_attach(d,len,AR_PPC_FALLBACK_MAX_STEPS"))
  self.assertLess(i.index("ar_bulk2_install_sha256(digest,sizeof(digest))"),
                  i.index("ar_ppc_fallback_attach(d,len,AR_PPC_FALLBACK_MAX_STEPS"))
  self.assertIn("ar_ppc_fallback_step",i)
  self.assertIn("ar_m712_exec_window(elf,elf_len,pc,window)",self.fallback)
  self.assertIn("if(ar_read32(pc)!=w)",self.fallback)
  self.assertIn("if(!divisor)return AR_PPC_UNSUPPORTED;",self.fallback)
  self.assertIn("case 459:",self.fallback)
  self.assertIn("case 235:",self.fallback)
  self.assertIn("case 8:",self.fallback)
  self.assertIn("default:return AR_PPC_UNSUPPORTED;",self.fallback)

 def test_ui_explicitly_hybrid_txt_and_no_rsx_game_claim(self):
  t=self.ui
  self.assertIn("ASCENSIONRECOMP M7.38",t)
  self.assertIn("M7.20 — DESPACHO HÍBRIDO EXPERIMENTAL",t)
  self.assertIn("measured.fallback_steps",t)
  self.assertIn("measured.fallback_unsupported_word",t)
  self.assertIn("AOT ARM64 + FALLBACK PPC EXPERIMENTAL",t)
  self.assertIn("initForExportingURLs:@[url] asCopy:YES",t)
  self.assertIn("RSX do Ascension: não demonstrado",t)
  self.assertIn("M7.19: +",self.build)
  self.assertIn("ppu_m720_fallback.o",self.build)
  self.assertIn("_ar_ppc_fallback_attach$",self.build)

if __name__=="__main__":
 unittest.main()
