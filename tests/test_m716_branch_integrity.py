"""M7.16 immutable source regressions alongside executable host PPC tests."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class BranchAOTM716(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aot=(ROOT/"runtime/ppu_m716_native_branch.c").read_text()
        cls.bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        cls.build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()

    def test_all_15_owner_reported_words_verified(self):
        expected=[
            "7bff0020","90dd000c","909d0014","90640000",
            "80bd0018","3c80009c","90650000","807d0018",
            "93fd0004","93fd0008","7fdf1810","88641780",
            "7bde0020","2c030000","41820018"]
        for w in expected:
            self.assertIn("0x"+w,self.aot)
        self.assertIn("ar_m712_exec_window",self.aot)
        self.assertIn("words[i+j]",self.aot)
        self.assertIn("ar_m716_register_block(d,len)",self.bridge)

    def test_real_branch_and_memory_fails_closed(self):
        self.assertIn("return AR_MEM_FAULT",self.aot)
        self.assertIn("rb>=ra ? XER_CA : 0u",self.aot)
        self.assertIn("c->cr=(c->cr & UINT32_C(0x0fffffff))",self.aot)
        self.assertIn("c->cia=(c->cr & UINT32_C(0x20000000)) ? PC_TAKEN:PC_NEXT;",self.aot)
        self.assertIn("0x003c4e14",self.aot)
        self.assertIn("0x003c4e00",self.aot)

    def test_final_iphone_binary_gate_and_public_ui(self):
        self.assertIn("ppu_m716_native_branch.o",self.build)
        self.assertIn("_ar_m716_aot_003c4dc4$",self.build)
        self.assertIn("M7.16: +1 verified native 15-instruction",self.build)
        self.assertIn('self.nativeLaunchButton=[self arLauncherButton:@"INICIAR JOGO"',self.ui)
        self.assertIn("PS3RECOMP / MÉTRICAS AO VIVO",self.ui)
        self.assertIn("Comandos RSX do jogo= NÃO COMPROVADOS",self.ui)

if __name__=="__main__":
    unittest.main()
