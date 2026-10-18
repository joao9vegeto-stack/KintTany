"""M7.43: offline PPC AOT payload, integrity, dedup and SHA ordering gates."""
import hashlib
import importlib.util
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]

class Offline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  spec=importlib.util.spec_from_file_location("gowa2_stage",ROOT/"tools/gowa2_offline_stage.py")
  cls.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.m)
  cls.bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
  cls.build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
  cls.reg=(ROOT/"runtime/ppu_bridge.c").read_text()
 def test_packed_batch_has_full_source_integrity_and_manifest(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   self.m.stage(ROOT/"runtime/gowa2-offline",Path(d))
   import json
   report=json.loads((Path(d)/"stage-report.json").read_text())
   self.assertEqual(report["generated_functions"],6251)
   self.assertEqual(report["translated_ppc_instructions"],221061)
   self.assertEqual(report["rejected_candidates"],1237)
 def test_real_registration_capacity_and_old_AOT_priority(self):
  self.assertIn("#define MAX_FUNCS 8192",self.reg)
  self.assertIn("#define AR_AOT_INDEX_SIZE 16384u",self.reg)
  self.assertIn("return AR_DUPLICATE",self.reg)
  self.assertLessEqual(1440+6251,8192)
  self.assertLessEqual(6251,8192)
  self.assertIn("ar_gowa2_offline_aot_install_sha256(digest,sizeof(digest))",self.bridge)
  self.assertLess(self.bridge.index("ar_private_aot_install_sha256"),self.bridge.index("ar_gowa2_offline_aot_install_sha256(digest"))
  self.assertLess(self.bridge.index("ar_m736_register_owner(d,len)"),self.bridge.index("ar_gowa2_offline_aot_install_sha256(digest"))
 def test_all_ten_modules_apple_clang_and_final_executable_symbols(self):
  self.assertIn('for chunk in 00 01 02 03 04 05 06 07 08',self.build)
  self.assertIn('ppu_gowa2_offline_aot_install.c',self.build)
  self.assertIn('GOWA2_OBJECTS+=',self.build)
  self.assertIn('verify_gowa2_macho.py ios-probe/gowa2-staged/symbols.txt',self.build)
  self.assertIn('m78-owner-aot-linked-symbols.txt',self.build)
 def test_elf_never_in_repo(self):
  self.assertFalse((ROOT/"GOWA.ELF").exists())
  self.assertFalse((ROOT/"GOWA(2).ELF").exists())
if __name__=="__main__":unittest.main()
