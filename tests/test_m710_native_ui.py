"""M7.11 native-first UI and signed PPU AOT CI regression."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]

class M710UI(unittest.TestCase):
    def test_launcher_exposes_native_entry_and_current_report(self):
        ui=(ROOT/"ios/ARProbeApp.m").read_text()
        self.assertIn('arLauncherLabel:@"ASCENSION"',ui)
        self.assertIn('brandSubtitle=[self arLauncherLabel:@"NPUA80918  ·  PS3 → iOS ARM64"',ui)
        self.assertIn('self.launcherReadinessLabel=[self arLauncherLabel:',ui)
        for key in (
            'self.nativeLaunchButton=[self arLauncherButton:@"INICIAR JOGO"',
            'self.ppuDiagnosticsButton=[self arLauncherButton:@"PROGRESSO REAL DA EXECUÇÃO"',
            "Chamadas de função AOT=%@",
            "action:@selector(shareAdvancedPpuReport:)",
            "PPC interpretado=0",
            "Primeiro flip guest apresentado= %@",
        ):
            self.assertIn(key,ui)
        bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        self.assertIn("ar_m772_run_entry(&ctx,image.entry_code)",bridge)
    def test_59_signed_real_entrypoints_and_sha(self):
        from tools.stage_m78_aot import ENTRY_PCS,EXPECTED_SHA256
        self.assertEqual(len(ENTRY_PCS),59)
        self.assertEqual(len(set(ENTRY_PCS)),59)
        self.assertEqual(EXPECTED_SHA256,
          "99c05272eddd827878983ddf6b3c85628ba04e027fded93d1c1dc26956c19a77")
        script=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        self.assertIn("59 REAL PPU ARM64 functions verified",script)
        self.assertIn("ios-probe/ppu_timebase.o",script)
        self.assertIn("_ar_ppu_timebase_ticks",script)
    def test_services_do_not_fake_sysmodule_load(self):
        bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        self.assertNotIn("0x32267a31u,ar_bind_hle",bridge)
        self.assertIn("ar_private_import_find_nid",bridge)

if __name__=="__main__":
    unittest.main()
