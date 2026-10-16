"""M5.7 fail-closed GPU blending and colour-mask probe."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
G=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
B=(ROOT/"tools/enable_ios_guest_draw_probe.py").read_text()
A=(ROOT/"ios/ARProbeApp.m").read_text()
W=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
class Blend(unittest.TestCase):
    def test_guest_pipeline(self):
        for token in ("NV4097_SET_BLEND_FUNC_SFACTOR,(sf<<16)|sf",
                      "NV4097_SET_BLEND_FUNC_DFACTOR,0x00010001u",
                      "NV4097_SET_BLEND_EQUATION,0x80068006u",
                      "m57_blend_mode==3u ? 0x00010000u : 0x01010101u",
                      "if(m57_blend_mode)return 0;",
                      "pixels[q]!=expected[i][q]",
                      "*blend_draws!=2u||*red_draws!=1u"):
            self.assertIn(token,G)
    def test_native_count_and_old_paths(self):
        for token in ("rs->eq_rgb==0x8006u","rs->color_mask==0x00010000u",
                      "ar_m57_blend_draws_encoded++","ar_m57_red_mask_draws_encoded++"):
            self.assertIn(token,B)
        for token in ("testM57BlendMask:","testM56StencilBitmasks:",
                      "testM55StencilMask:","testM54DepthOcclusion:"):
            self.assertIn(token,A)
        self.assertIn("AscensionRecompProbe-0.6.1-unsigned.ipa",W)
if __name__=="__main__":unittest.main()
