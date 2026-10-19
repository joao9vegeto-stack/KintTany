"""M7.41 validates PS3 .SFO arbitrary item picker and ISA hint support.

No claims of permission bypass between app sandboxes.
"""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class M741(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ui=(R/"ios/ARProbeApp.m").read_text()
  cls.fallback=(R/"runtime/ppu_m720_fallback.c").read_text()
  cls.workflow=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
 def test_sfo_unknown_extension_without_any_copy(self):
  self.assertIn("initForOpeningContentTypes:@[UTTypeItem] asCopy:YES",self.ui)
  self.assertIn("Importar PARAM.SFO · cópia temporária",self.ui)
  self.assertIn("ARGameFolderInspectParamSFO(marker,&error)",self.ui)
  self.assertIn("initForOpeningContentTypes:@[UTTypeData] asCopy:YES",self.ui)
  self.assertNotIn("initForOpeningContentTypes:@[UTTypeData] asCopy:NO",self.ui)
  self.assertIn("Permissão USRDIR ainda NÃO obtida",self.ui)
 def test_real_opcode_not_unknown_nop(self):
  self.assertIn("case 278:case 246:",self.fallback)
  self.assertIn("if(record)return AR_PPC_UNSUPPORTED;",self.fallback)
  self.assertIn("c->cia=pc+4u;",self.fallback)
  self.assertIn("tests/host_m741_ppc_dcbt.c",self.workflow)
 def test_build(self):
  self.assertIn("<string>7640</string>",(R/"ios/Probe-Info.plist").read_text())
  self.assertIn("AscensionRecomp-M7.61-BULK-AOT-AppleARM64",self.workflow)
if __name__=="__main__":unittest.main()
