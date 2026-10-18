"""M7.40: existing RPCS3 NPUA80918 game installation, no duplicated assets."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class M740ReadOnly(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()
  cls.folder=(ROOT/"ios/ARGameFolderStore.m").read_text()
  cls.header=(ROOT/"ios/ARGameFolderStore.h").read_text()
  cls.workflow=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
 def test_picker_opens_existing_param_without_copy(self):
  u=self.ui
  self.assertIn("Abrir PARAM.SFO do RPCS3 · sem cópia",u)
  self.assertIn("initForOpeningContentTypes:@[UTTypeItem] asCopy:NO",u)
  self.assertIn("self.rpcMarkerPicker=picker",u)
  self.assertIn("ARGameFolderProbeRPCS3Marker(marker,&error)",u)
  self.assertIn("@[rpcMarkerButton,folderButton,elfButton]",u)
  self.assertNotIn("@[localFolderButton,folderButton,elfButton]",u)
  self.assertIn("ESCOPO RPCS3 RESTRITO",u)
 def test_readonly_and_scope_failure_are_explicit(self):
  src=self.folder
  for token in (
     "ARGameFolderProbeRPCS3Marker", "NSFileCoordinatorReadingWithoutChanges",
     "coordinateReadingItemAtURL:paramSfo",
     "startAccessingSecurityScopedResource", "stopAccessingSecurityScopedResource",
     "@\"data\",@\"dev_hdd0\",@\"game\"",
     "USRDIR", "param_sfo_prefix_bytes", "folder_access_verified",
     "read_only", "no_copy", "gameError(44",
  ): self.assertIn(token,src)
  self.assertIn("ARGameFolderProbeRPCS3Marker",self.header)
  self.assertNotIn("writeToURL:paramSfo",src)
  self.assertNotIn("removeItemAtURL:paramSfo",src)
  self.assertNotIn("moveItemAtURL:paramSfo",src)
 def test_synthetic_host_checks_original_files_unchanged(self):
  self.assertIn("tests/host_m740_rpcs3_inplace.m",self.workflow)
  self.assertIn("m740-rpcs3-inplace-host",self.workflow)
  c=(ROOT/"tests/host_m740_rpcs3_inplace.m").read_text()
  self.assertIn("[sfoAfter isEqualToData:sfo]",c)
  self.assertIn("[assetAfter isEqualToData:payload]",c)
  plist=(ROOT/"ios/Probe-Info.plist").read_text()
  self.assertIn("<string>83</string>",plist)

if __name__=="__main__":unittest.main()
