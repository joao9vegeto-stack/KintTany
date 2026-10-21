import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IOSRSXPumpContractTests(unittest.TestCase):
    def test_native_game_loop_drains_fifo_and_presents_flips(self):
        source = (ROOT / "ios/ARProbeApp.m").read_text()
        start = source.index("- (void)runNativeRSXPump {")
        end = source.index("- (void)showNativeGameFrame {", start)
        pump = source[start:end]
        self.assertIn("cellGcm_rsx_process_fifo()", pump)
        self.assertIn("cellGcm_take_flip_pending_synced()", pump)
        self.assertIn("rsx_metal_backend_present()", pump)
        self.assertIn("ARNativeRSXPresentedFrames", pump)
        self.assertNotIn("rsx_metal_backend_note_guest_frame", pump)

    def test_final_macho_gate_checks_renderer_used_by_game_loop(self):
        script = (ROOT / "tools/build_ios_probe_ipa.sh").read_text()
        self.assertIn('"_rsx_metal_backend_init"', script)
        self.assertIn('"_rsx_metal_backend_present"', script)
        self.assertIn('"_rsx_metal_backend_guest_draws"', script)
        self.assertNotIn('"_rsx_metal_backend_note_guest_frame"', script)
