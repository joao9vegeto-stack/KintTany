"""M7.47 real import path, FMR AOT, source-vs-owner ELF bounds tests."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class M747(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()
  cls.folder=(ROOT/"ios/ARGameFolderStore.m").read_text()
  cls.bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
  cls.native=(ROOT/"runtime/ppu_m747_native_fmr.c").read_text()
  cls.fallback=(ROOT/"runtime/ppu_m720_fallback.c").read_text()
  cls.workflow=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
 def test_picker_matches_successful_elf_copy_mode(self):
  self.assertIn("initForOpeningContentTypes:@[UTTypeData] asCopy:YES",self.ui)
  self.assertIn("initForOpeningContentTypes:@[UTTypeItem] asCopy:YES",self.ui)
  self.assertIn("ARGameFolderInspectParamSFO(marker,&error)",self.ui)
  self.assertIn("ARGameFolderPrepareDocumentsHome(&homeError)",self.ui)
  self.assertIn("ARGameFolderImport(chosen,&error)",self.ui)
 def test_param_psf_parsed_without_claiming_folder_permission(self):
  for name in ("ARGameFolderInspectParamSFO","TITLE_ID","NPUA80918",
               "NSFileCoordinatorReadingWithoutChanges","psf32","memchr",
               "folder_access_verified"):
   self.assertIn(name,self.folder)
  self.assertIn("@NO",self.folder)
  self.assertIn("Documents",self.ui)
 def test_native_fmr_and_generic_lifter(self):
  for name in ("ar_m747_native_003eef0c","ar_m747_native_003eef20",
               "0xf310084da346e99f","0xedbe0d6ca5406688",
               "ar_m712_exec_window","ar_register","ar_guest_call"):
   self.assertIn(name,self.native)
  self.assertIn("xo==72u && a==0u",self.fallback)
  self.assertIn("ar_fp_setraw(c,d,ar_fp_raw64(c,b))",self.fallback)
  self.assertLess(self.bridge.index("ar_gowa2_offline_aot_install_sha256(digest"),
                  self.bridge.index("ar_m747_register_owner(d,len)"))
  lifter=(ROOT/"tools/ppu_cfg_lifter.py").read_text()
  self.assertIn("if xo==72 and a==0:",lifter)
 def test_ci_real_host_and_cross_compile(self):
  for tok in ("tests/host_m747_native_fmr.c","tests/host_m747_param_sfo.m",
              "m747-native-host.log","m747-param-host.log",
              "m747-native-arm64.o"):
   self.assertIn(tok,self.workflow)
  self.assertIn("<string>7650</string>",(ROOT/"ios/Probe-Info.plist").read_text())
if __name__=="__main__":unittest.main()
