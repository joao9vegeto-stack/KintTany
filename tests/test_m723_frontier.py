"""M7.23: one original ELF native AOT + old 1418, private secret only.

Uses synthetic/invalid Base64 solely for validation; no copyrighted C or ELF
is exposed in repository, CI artifacts or test source.
"""
from pathlib import Path
import importlib.util
import unittest

BASE=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location("m723",BASE/"tools/stage_m723_owner_frontier.py")
stage=importlib.util.module_from_spec(sp)
sp.loader.exec_module(stage)

class FrontierStageM723(unittest.TestCase):
 def test_owner_sha_and_exact_target(self):
  self.assertEqual(stage.ELF_SHA256,"4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5")
  self.assertEqual(stage.SOURCE_SHA256,"ed8955f008960f86326e04672fdde5362474217a8e0a3d4e07bd1c8697f70bed")
  self.assertEqual(stage.ENTRY,"003c511c")
  self.assertEqual(stage.AOT_NAME,"ar_m722_ppu_003c511c")
  self.assertEqual(stage.INSTALLER_NAME,"ar_m722_install_sha256")
 def test_secret_fail_closed(self):
  for secret in [""," ","!!", "A"*8193]:
   with self.assertRaises(ValueError):
    stage.stage_decode(secret)
 def test_fourth_secret_and_linking_leave_earlier_1418_untouched(self):
  bridge=(BASE/"ios/ARLivePPUBridge.c").read_text()
  build=(BASE/"tools/build_ios_probe_ipa.sh").read_text()
  workflow=(BASE/".github/workflows/ascension-recomp-m0.yml").read_text()
  ui=(BASE/"ios/ARProbeApp.m").read_text()
  for name in ["ar_private_aot_install_sha256","ar_bulk_install_sha256",
               "ar_bulk2_install_sha256","ar_m722_install_sha256"]:
   self.assertIn(name+"(digest,sizeof(digest))",bridge)
  self.assertIn("ASCENSION_PRIVATE_FRONTIER_AOT_LINKED",bridge)
  for name in ["AscensionPrivateAOT.o","AscensionPrivateBulk.o",
               "AscensionPrivateBulk2.o","AscensionPrivateFrontier.o"]:
   self.assertIn(name,build)
  self.assertIn("_ar_m722_ppu_003c511c$",build)
  self.assertIn("grep -Eq ' [Tt] _ar_m722_ppu_003c511c$' m723-frontier-object-symbols.txt",build)
  self.assertIn("grep -Eq ' [Tt] _ar_m722_install_sha256$' m723-frontier-object-symbols.txt",build)
  self.assertEqual(build.count("# Stage the native PPU bridge"),1)
  self.assertLess(len(build.splitlines()),1000)
  self.assertEqual(build.count("ppu_m734_native_math.c"),1)
  self.assertEqual(build.count("ppu_m734_native_batch.c"),1)
  self.assertIn("ASCENSION_AOT_FRONTIER_GZIP_B64",workflow)
  self.assertIn('ASCENSIONRECOMP M7.47',ui)
  self.assertIn('initForExportingURLs:@[url] asCopy:YES',ui)
  self.assertIn('RSX do Ascension: não demonstrado',ui)
 def test_prior_manifest_strict_parsing(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   name=Path(d)/"prior.txt"
   name.write_text("ar_game_ppu_00010410\nar_bulk_ppu_003c4e14\nar_bulk2_ppu_002c16a4\n",encoding="ascii")
   self.assertEqual(stage.prior_aot_entries([str(name)]),
                    {"00010410","003c4e14","002c16a4"})
   name.write_text("ar_game_ppu_00010410\nmalformed\n",encoding="ascii")
   with self.assertRaises(ValueError):
    stage.prior_aot_entries([str(name)])

if __name__=="__main__":unittest.main()
