"""M5.8 fail-closed guest fragment alpha test smoke guards."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
G=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
M=(ROOT/"tools/enable_ios_guest_draw_probe.py").read_text()
A=(ROOT/"ios/ARProbeApp.m").read_text()
W=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
class AlphaTest(unittest.TestCase):
    def test_genuine_guest_methods(self):
        for token in ("NV4097_SET_ALPHA_FUNC,func[i]",
                      "NV4097_SET_ALPHA_REF,ref[i]",
                      "NV4097_SET_ALPHA_TEST_ENABLE,1u",
                      "NV4097_SET_ALPHA_TEST_ENABLE,0u",
                      "0x0204u,0x0201u,0x0204u,0x0204u",
                      "128u,128u,255u,0u",
                      "m58_alpha_phase>=2u", "x>=4u ? 255u : 0u",
                      "(!m58_alpha_phase || m58_alpha_phase==1u)",
                      "m58_alpha_phase=0u"):
            self.assertIn(token,G)
    def test_pixel_proof_and_prior_unchanged(self):
        for token in ("ar_probe_m58_guest_alpha_test",
                      "for(unsigned i=0;i<5u;i++)",
                      "pixels[q]!=expected[i][q]",
                      "0xff0000ffu,0xffff0000u,0xffff0000u,0xff0000ffu",
                      "*alpha_draws!=4u",
                      "ar_probe_m57_guest_blend_mask",
                      "ar_probe_m56_guest_stencil_bitmasks",
                      "ar_probe_m55_guest_stencil_mask"):
            self.assertIn(token,G)
    def test_native_metal_and_ui(self):
        for token in ("strstr(ps_hlsl, \"fp_alpha.x\")",
                      "strstr(ps_hlsl, \"discard;\")",
                      "p->ar_m51_tex0 && p->ar_m58_alpha_test",
                      "ar_m58_alpha_draws_encoded++"):
            self.assertIn(token,M)
        self.assertNotIn("computeCommandEncoder",G)
        for token in ("testM58AlphaTest:","testM57BlendMask:",
                      "testM56StencilBitmasks:","testM55StencilMask:"):
            self.assertIn(token,A)
        self.assertIn("AscensionRecompProbe-0.6.1-unsigned.ipa",W)
if __name__=="__main__":unittest.main()
