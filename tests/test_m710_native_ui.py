"""M7.10 native-first UI and signed PPU AOT CI regression."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]

class M710UI(unittest.TestCase):
    def test_native_first_retains_legacy_in_advanced_view(self):
        ui=(ROOT/"ios/ARProbeApp.m").read_text()
        self.assertIn('header.text=@"ASCENSIONRECOMP   ·   M7.10"',ui)
        for key in (
            "Entradas AOT vinculadas: %u",
            "Diagnóstico avançado · M6/M7",
            "self.status.text=self.ppuSummary;",
            "ar_private_import_match(data.bytes,data.length,native[7]",
            "Copiar status AOT",
            "Copiar tudo",
            "M7.2 — EXECUÇÃO PPU CONTÍNUA",
            "M7.3 — IMPORTAÇÃO PRX",
            "M6.7.6 / NPUA80918",
            "self.ppuAdvancedButton.enabled=YES",
        ):
            self.assertIn(key,ui)
        self.assertIn('self.ppuReport=[NSString stringWithFormat:@"%@',ui)
    def test_41_signed_real_entrypoints_and_sha(self):
        from tools.stage_m78_aot import ENTRY_PCS,EXPECTED_SHA256
        self.assertEqual(len(ENTRY_PCS),41)
        self.assertEqual(len(set(ENTRY_PCS)),41)
        self.assertEqual(EXPECTED_SHA256,
          "2f2a28334e96bafcb9d0d8920b5372b978646ad22e1b5c4681e0a03aac61747d")
        script=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        self.assertIn("41 REAL PPU ARM64 functions verified",script)
        self.assertIn("ios-probe/ppu_timebase.o",script)
        self.assertIn("_ar_ppu_timebase_ticks",script)
    def test_services_do_not_fake_sysmodule_load(self):
        bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        self.assertNotIn("0x32267a31u,ar_bind_hle",bridge)
        self.assertIn("ar_private_import_find_nid",bridge)

if __name__=="__main__":
    unittest.main()
