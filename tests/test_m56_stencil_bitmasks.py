"""M5.6: synthetic full-screen GPU probe must fail closed for masked Z24S8."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
G=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
B=(ROOT/"tools/enable_ios_guest_draw_probe.py").read_text()
U=(ROOT/"ios/ARProbeApp.m").read_text()
W=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
class StencilBitPlanes(unittest.TestCase):
    def test_guest_registers_and_persistent_stencil(self):
        for value in ("depth_mode==6u", "M55_NV4097_SET_STENCIL_MASK,write_mask",
                      "NV4097_SET_STENCIL_FUNC_MASK,read_mask",
                      "j==0u ? 0x0fu", "j==3u ? 0xf0u",
                      "j==6u ? 0x0fu", "m56_ref[7]",
                      "0xb0u,0xb5u,0x05u,0x05u",
                      "depth_mode==3u || depth_mode==6u"):
            self.assertIn(value,G)
    def test_all_seven_ordered_gpu_colour_checks(self):
        for value in ("ar_probe_m56_guest_stencil_bitmasks(",
                      "palette[7]={0u,1u,2u,3u,0u,1u,2u}",
                      "expected[7]={0u,0u,2u,3u,0u,0u,2u}",
                      "i<7u", "6u+i,pixels,&encoded,&guest,shader",
                      "ar_probe_m55_stencil_draws()",
                      "pixels[q]!=m51_colors[(q+expected[i])&3u]",
                      "*stencil_draws!=7u", "*guest_total!=7u"):
            self.assertIn(value,G)
    def test_metal_recording_and_legacy_ui(self):
        for value in ("rs->s_write_mask == 0xffu",
                      "rs->s_write_mask == 0x0fu",
                      "rs->s_write_mask == 0xf0u",
                      "rs->s_func_mask == 0x0fu",
                      "p->ar_m55_stencil", "p->ar_m51_tex0"):
            self.assertIn(value,B)
        self.assertNotIn("computeCommandEncoder",B)
        for value in ("testM56StencilBitmasks:","testM55StencilMask:",
                      "testM54DepthOcclusion:","testM53Multipass:"):
            self.assertIn(value,U)
        self.assertIn("host_m56_stencil_masks.c",W)
        self.assertIn("AscensionRecompProbe-0.6.12-unsigned.ipa",W)
if __name__=="__main__":unittest.main()
