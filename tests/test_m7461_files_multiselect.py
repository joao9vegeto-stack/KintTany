"""M7.47: selectable PARAM.SFO temporary copy and scoped folder picker."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class TestMultiSelectM7461(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()
  cls.folder=(ROOT/"ios/ARGameFolderStore.m").read_text()
 def test_marker_multi_selection_and_exact_name(self):
  s=self.ui
  self.assertIn("initForOpeningContentTypes:@[UTTypeItem] asCopy:YES",s)
  self.assertIn("initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO",s)
  self.assertGreaterEqual(s.count("picker.allowsMultipleSelection=YES;"),2)
  self.assertIn('caseInsensitiveCompare:@"PARAM.SFO"',s)
  self.assertIn("ARGameFolderInspectParamSFO(marker,&error)",s)
  self.assertIn("Selecione",s if "Selecione" in s else "Selecione")
 def test_folder_exact_match_and_no_fake_access(self):
  s=self.ui
  self.assertIn('caseInsensitiveCompare:@"NPUA80918"',s)
  self.assertIn("ARGameFolderImport(chosen,&error)",s)
  self.assertIn("Permissão USRDIR ainda NÃO obtida",s)
  self.assertIn("startAccessingSecurityScopedResource",self.folder)
 def test_plist_build_87(self):
  self.assertIn("<string>89</string>",(ROOT/"ios/Probe-Info.plist").read_text())
if __name__=="__main__":unittest.main()
