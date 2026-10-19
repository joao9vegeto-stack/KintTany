"""M7.11 signed native game AOT and sparse PS3 guest virtual memory."""
from pathlib import Path
import unittest
from tools.stage_m78_aot import ENTRY_PCS, EXPECTED_SHA256
ROOT=Path(__file__).resolve().parents[1]
class M711(unittest.TestCase):
    def test_exact_compiled_game_entry_manifest(self):
        self.assertEqual(len(ENTRY_PCS),59)
        self.assertEqual(len(set(ENTRY_PCS)),59)
        self.assertIn(0x002c164c,ENTRY_PCS)
        self.assertEqual(EXPECTED_SHA256,
          "99c05272eddd827878983ddf6b3c85628ba04e027fded93d1c1dc26956c19a77")
        build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        self.assertIn("59 REAL PPU ARM64 functions verified",build)
        self.assertIn("m711_bind_memory",build)
        self.assertIn("ppu_mmapper_map",build)
    def test_native_services_and_sparse_memory(self):
        bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        mem=(ROOT/"runtime/ppu_bridge.c").read_text()
        sys=(ROOT/"runtime/ppu_native_sysutil.c").read_text()
        self.assertIn("ar_m711_bind_memory(d,len,out)",bridge)
        self.assertIn("ar_m711_bind_sysutil(d,len,out)",bridge)
        self.assertIn("ar_mmapper_reset()",bridge)
        self.assertIn("ar_vm_external_map(uint32_t",mem)
        self.assertIn("ar_vm_external_unmap(uint32_t",mem)
        self.assertIn("ar_sysutil_bind_core",sys)
        self.assertIn("if(mask!=15u)",sys)
    def test_native_first_ui_retained(self):
        ui=(ROOT/"ios/ARProbeApp.m").read_text()
        self.assertIn('header.text=[NSString stringWithFormat',ui)
        self.assertIn("SYSUTIL core vinculado",ui)
        self.assertIn("Diagnóstico avançado · M6/M7",ui)
