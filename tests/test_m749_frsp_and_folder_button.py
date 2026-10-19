"""M7.49: actual visible detection, owner FPR ISA, and unchanged folders."""
import sys
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"tools"))
from ppu_cfg_lifter import lift,Unsupported
BLR=0x4e800020
class M749Regressions(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ui=(R/"ios/ARProbeApp.m").read_text()
  cls.fp=(R/"runtime/ppu_fp_scalar.h").read_text()
  cls.fallback=(R/"runtime/ppu_m720_fallback.c").read_text()
  cls.bridge=(R/"ios/ARLivePPUBridge.c").read_text()
  cls.workflow=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
 def test_local_detection_button_is_arranged(self):
  self.assertIn("localFolderButton,folderButton,elfButton",self.ui)
  self.assertIn("Detectar arquivos locais · NPUA80918",self.ui)
  self.assertIn("[localFolderButton addTarget:self action:@selector(importGameFolderFromDocuments:)",self.ui)
  self.assertIn("ARGameFolderImportLocalDocuments(&error)",self.ui)
  self.assertIn("ARGameFolderReadPrefix(relative,4u,&readError)",self.ui)
 def test_frsp_generic_isa(self):
  word=0xfc200818
  src,h=lift([word,BLR],0x10000)
  self.assertEqual(h["frsp"],1)
  self.assertIn("ar_fp_frsp(c,1,1)",src)
  self.assertIn("ppu_fp_scalar.h",src)
  self.assertIn("xo==12u && a==0u",self.fallback)
  self.assertIn("ar_fp_frsp(c,d,b)",self.fallback)
  self.assertIn("fegetround()!=FE_TONEAREST",self.fp)
  with self.assertRaises(Unsupported):
   lift([word|1,BLR],0x10000)
 def test_owner_native_and_ci(self):
  source=(R/"runtime/ppu_m749_native_frsp.c").read_text()
  self.assertIn("0xb452445b9eadfb69",source)
  self.assertIn("ar_m712_exec_window",source)
  self.assertIn("ar_read32",source)
  self.assertLess(self.bridge.index("ar_gowa2_offline_aot_install_sha256(digest"),
                  self.bridge.index("ar_m749_register_frsp(d,len)"))
  for s in ("m749-frsp-host.log","tests/host_m749_native_frsp.c",
            "m749-frsp-arm64.o","_ar_m749_register_frsp"):
   self.assertIn(s,self.workflow)
  self.assertIn("<string>7660</string>",(R/"ios/Probe-Info.plist").read_text())
if __name__=="__main__":unittest.main()
