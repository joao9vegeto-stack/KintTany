"""M7.59 source-reproducible real owner PPC conditional AOT integration."""
from pathlib import Path
import sys,unittest,hashlib,struct
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from generate_m759_owner_aot import PC,END,WORDS,BE_SHA,generate
class M759(unittest.TestCase):
 def test_owner_range_hash_and_native_boundaries(self):
  self.assertEqual((PC,END,len(WORDS)),(0x002c1378,0x002c1420,42))
  self.assertEqual(hashlib.sha256(struct.pack('>42I',*WORDS)).hexdigest(),BE_SHA)
  src,meta=generate()
  self.assertEqual(meta["number_words"],42)
  self.assertEqual(meta["next_pc"],"0x002c14a4")
  self.assertGreaterEqual(meta["guest_memory_ops"],10)
  for needle in ("ar_m759_native_002c1378","ar_m759_register_owner",
                 "ar_guest_call(c,0x52b840ULL)",
                 "c->cia=0x2c14a4ULL; return 1;",
                 "c->cia=0x2c1420ULL; return 1;",
                 "ar_m712_exec_window","ar_read32(addr)"):
   self.assertIn(needle,src)
  self.assertNotIn("ar_ppc_fallback",src)
 def test_generic_lifter_opt_in_never_weakens_existing_boundary(self):
  from ppu_cfg_lifter import lift,Unsupported
  with self.assertRaises(Unsupported):
   lift(WORDS,PC,"test_strict")
  code,_=lift(WORDS,PC,"test_native",allow_terminal_conditional=True)
  self.assertIn("c->cia=0x2c1420ULL; return 1;",code)
 def test_app_links_hosted_original_and_guest_fs_stays_evidence_based(self):
  bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
  build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
  ci=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
  ui=(ROOT/"ios/ARProbeApp.m").read_text()
  self.assertIn("ar_m759_register_owner(d,len)",bridge)
  self.assertIn("python3 tools/generate_m759_owner_aot.py",build)
  self.assertIn("ppu_m759_generated.o",build)
  self.assertIn("_ar_m759_native_002c1378",build)
  self.assertIn("host_m759_generated.c",ci)
  self.assertIn("m759-host.log",ci)
  self.assertIn("M7.59 (teste físico",ui)
  self.assertIn("cellFsRead com bytes positivos",ui)
  self.assertNotIn("    ios-probe/ppu_m720_fallback.o \\",build)
if __name__=="__main__":unittest.main()
