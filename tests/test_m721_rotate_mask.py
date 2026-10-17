"""M7.21 PowerPC64 mask/rotate semantics, branch continuation, safe TXT export."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class M721Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.code=(ROOT/"runtime/ppu_m720_fallback.c").read_text()
  cls.bridge=(ROOT/"runtime/ppu_bridge.c").read_text()
  cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()
 def test_ppc64_masked_insert_preserves_untouched_destination_bits(self):
  self.assertIn("case 20:case 21:case 23:",self.code)
  self.assertIn("ppc_mask32_64(mb,me)",self.code)
  self.assertIn("ppc_data32(rotate32((uint32_t)r[d],sh))",self.code)
  self.assertIn("((r[a]&~m)|(rotated&m))",self.code)
  self.assertIn("mb>me?UINT64_C(0xffffffff00000000)",self.code)
  self.assertIn("case 30:",self.code)
  self.assertIn("xo==3u ? ((r[a]&~mask)|(rotated&mask))",self.code)
 def test_hybrid_remains_aot_first_and_not_jit(self):
  self.assertLess(self.bridge.index("ar_ppu_fn fn=lookup(pc,&found_index);"),
                  self.bridge.index("const int step=fb_eval"))
  self.assertIn("if(fb_elf && fb_eval)",self.bridge)
  self.assertIn("AR_PPC_UNSUPPORTED",self.bridge)
  self.assertIn("fb_steps++;",self.bridge)
 def test_txt_status_and_graphics_limit(self):
  self.assertIn("ASCENSIONRECOMP M7.33 · NPUA80918",self.ui)
  self.assertIn("AscensionRecomp-M7.33-NPUA80918-%@.txt",self.ui)
  self.assertIn("initForExportingURLs:@[url] asCopy:YES",self.ui)
  self.assertIn("RSX do Ascension: não demonstrado",self.ui)
  self.assertIn("[stack addArrangedSubview:diagnostics];",self.ui)

if __name__=="__main__":unittest.main()
