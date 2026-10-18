"""M7.38: regressions found in physical iPhone M7.37 export.

Owner loader -38 must not result from 16384-step request while
bridge hard-rejects greater than 4096. F0 UI must export errors.
"""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]

class M738Checks(unittest.TestCase):
 def test_runtime_and_ios_limit_agree(self):
  h=(R/"runtime/ppu_bridge.h").read_text()
  c=(R/"runtime/ppu_bridge.c").read_text()
  b=(R/"ios/ARLivePPUBridge.c").read_text()
  self.assertIn("#define AR_PPC_FALLBACK_MAX_STEPS 16384u",h)
  self.assertIn("limit>AR_PPC_FALLBACK_MAX_STEPS",c)
  self.assertNotIn("limit>4096u",c)
  self.assertIn("ar_ppc_fallback_attach(d,len,AR_PPC_FALLBACK_MAX_STEPS",b)
  self.assertIn("ar_run(&ctx,image.entry_code,32768u)",b)
 def test_folder_failure_is_exported_and_picker_discoverable(self):
  ui=(R/"ios/ARProbeApp.m").read_text()
  self.assertIn("Selecionar pasta NPUA80918 · Abrir",ui)
  self.assertIn("initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO",ui)
  self.assertIn("Selecione NPUA80918 e toque Abrir",ui)
  self.assertIn("M7.38 F0 — FALHA IMPORTAÇÃO PASTA",ui)
  self.assertIn("self.folderReport=report",ui)
  self.assertIn("self.folderReport=[NSString stringWithFormat:",ui)
  self.assertIn("body,self.folderReport",ui)
 def test_mac_host_enforces_limit_with_real_runtime(self):
  w=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  self.assertIn("tests/host_m738_fallback_limit.c",w)
  self.assertIn("m738-runtime-attach-host",w)
  self.assertIn("0.6.22-unsigned.ipa",w)
  self.assertIn("<string>90</string>",(R/"ios/Probe-Info.plist").read_text())

if __name__=="__main__":
 unittest.main()
