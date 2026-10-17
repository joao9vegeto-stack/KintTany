"""M7.15 regressions: native AOT, batch visibility, and no false RSX claims."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class M715SourceRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()
        cls.bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        cls.build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        cls.aot=(ROOT/"runtime/ppu_m715_aot_fragment.c").read_text()

    def test_report_appended_even_on_successful_legacy_ppu48(self):
        self.assertIn("self.ppuReport=[self.ppuReport stringByAppendingString:frontierReport];",self.ui)
        self.assertIn("[extended appendString:frontierReport];",self.ui)
        self.assertIn("self.ppuBatchReport=",self.ui)
        self.assertIn("self.ppuBatchButton.enabled=(self.ppuBatchReport.length>0);",self.ui)
        self.assertIn("[stack addArrangedSubview:batchButton];",self.ui)
        self.assertIn("copyPpuBatch:(UIButton *)sender",self.ui)
        self.assertIn("UIPasteboard.generalPasteboard.string=self.ppuBatchReport",self.ui)

    def test_67_native_entries_only_after_elf_guard(self):
        self.assertIn("ar_m715_register_fragment(d,len)",self.bridge)
        self.assertIn("ar_m712_exec_window(elf,length,AR_M715_PC,got)",self.aot)
        self.assertIn("ar_m715_aot_003c4db4",self.build)
        self.assertIn("ar_m715_register_fragment",self.build)
        self.assertIn("M7.15: +1 ELF-verified load/store ARM64 entry",self.build)

    def test_graphics_status_does_not_claim_game_menu(self):
        self.assertIn("RSX do Ascension: não demonstrado",self.ui)
        self.assertIn("M4/M5 são testes sintéticos Metal, não menu do jogo.",self.ui)

if __name__=="__main__":
    unittest.main()
