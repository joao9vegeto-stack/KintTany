"""M7.37 F0: real user-selected local folder plumbing and PPU scale guard.

No commercial files: CI compiles Foundation code against synthetic files.
"""
from pathlib import Path
import unittest

R=Path(__file__).resolve().parents[1]
class TestM737Folder(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ui=(R/"ios/ARProbeApp.m").read_text()
  cls.impl=(R/"ios/ARGameFolderStore.m").read_text()
  cls.header=(R/"ios/ARGameFolderStore.h").read_text()
  cls.bridge=(R/"ios/ARLivePPUBridge.c").read_text()
  cls.fallback=(R/"runtime/ppu_m720_fallback.c").read_text()
  cls.script=(R/"tools/build_ios_probe_ipa.sh").read_text()
  cls.workflow=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
 def test_folder_picker_is_in_real_game_tab_and_independent_of_elf(self):
  for token in (
    "Selecionar pasta NPUA80918", "initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO",
    "self.folderPicker=picker;", "controller==self.folderPicker",
    "ARGameFolderImport(chosen,&error)", "@[rpcMarkerButton,localFolderButton,folderButton,elfButton]",
    "dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0)"
  ):
   self.assertIn(token,self.ui)
  self.assertIn("ARGameFolderRestore(NULL)",self.ui)
  self.assertIn("ARGameFolderReadPrefix(relative,4u,&readError)",self.ui)
 def test_security_and_privacy_measures(self):
  for token in (
    "NSURLBookmarkCreationMinimalBookmark", "startAccessingSecurityScopedResource",
    "stopAccessingSecurityScopedResource", "NSURLIsSymbolicLinkKey",
    "game-folder-manifest.json", "safeRelativePath",
    "NSURLIsExcludedFromBackupKey", "readDataUpToLength:maxLength",
    "ARGameFolderReadPrefix", "200000u"
  ):
   self.assertIn(token,self.impl)
  self.assertNotIn("GOWA.ELF",self.impl)
  self.assertNotIn("PSARC game",self.impl)
 def test_no_fake_guest_sys_fs_and_no_aot_inflation(self):
  self.assertIn("cellFsOpen/cellFsRead ainda NÃO executadas",self.ui)
  self.assertIn("ARGameFolderImport",self.header)
  self.assertIn("case 7:{ /* mulli",self.fallback)
  self.assertIn("case 8:{ /* subfic",self.fallback)
  self.assertIn("case 9:case 73:",self.fallback)
  self.assertIn("case 233:",self.fallback)
  self.assertIn("ar_ppc_fallback_attach(d,len,AR_PPC_FALLBACK_MAX_STEPS",self.bridge)
  self.assertIn("ar_run(&ctx,image.entry_code,32768u)",self.bridge)
  self.assertIn("ios/ARGameFolderStore.m",self.script)
 def test_host_evidence_required_not_decorative(self):
  for token in ("tests/host_m737_gamefolder.m","m737-folder-host",
                "tests/host_m737_ppc_scale.c","m737-ppu-host",
                "AscensionRecomp-M7.49-GOWA-6251-AOT-FRSP-AppleARM64"):
   self.assertIn(token,self.workflow)
  self.assertIn("0.6.21",self.script)

if __name__=="__main__":
 unittest.main()
