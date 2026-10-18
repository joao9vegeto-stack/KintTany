"""M5.4 depth correctness must come from iPhone Metal pixels."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ActualDepthContract(unittest.TestCase):
    def test_distinct_depth_values_correct_expected_pixels(self):
        s=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
        for token in (
            "ar_probe_m54_guest_depth_occlusion",
            "const float depths[3]={0.45f,0.85f,0.10f}",
            "const unsigned palettes[3]={0u,1u,2u}",
            "const unsigned expected[3]={0u,0u,2u}",
            "depth_mode ? (0x5u | (2u<<5)) : 0x5u",
            "NV4097_SET_SURFACE_ZETA_OFFSET,M54_Z_OFFSET",
            "NV4097_SET_DEPTH_FUNC,0x0201u",
            "NV4097_SET_DEPTH_TEST_ENABLE,1u",
            "if (!depth_mode)\n        rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,0u);",
            "depth_mode ? 0xf1u : 0xf0u",
            "pixels[q]!=m51_colors[(q+expected[i])&3u]",
            "if(*depth_draws!=3u) return -440"):
            self.assertIn(token,s)
    def test_shader_and_gpu_proof_not_host_shortcuts(self):
        s=(ROOT/"tools/enable_ios_guest_draw_probe.py").read_text()
        for token in ("ar_m54_depth_draws_encoded",
                      "p->ar_m54_depth_less",
                      "r->depth && eng_obj(r->depth)",
                      "rs->depth_test && rs->depth_write && rs->depth_func == 0x0201u"):
            self.assertIn(token,s)
        self.assertNotIn("computeCommandEncoder",s)
    def test_preserve_previous_probes(self):
        s=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
        for token in ("ar_probe_m53_guest_multipass","ar_probe_m52_guest_texture_mutation",
                     "ar_probe_m51_guest_textured_quad",
                     "0.0f,0u,pixels,encoded,guest_draws,shader_state"):
            self.assertIn(token,s)
        app=(ROOT/"ios/ARProbeApp.m").read_text()
        for token in ("testM54DepthOcclusion:","testM53Multipass:",
                      "testM52TextureMutation:","testM51GuestDraw:","testRSXCache:"):
            self.assertIn(token,app)
        wf=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
        self.assertIn("AscensionRecompProbe-0.6.21-unsigned.ipa",wf)
        self.assertIn("m54-status.txt",wf)
if __name__=="__main__": unittest.main()
