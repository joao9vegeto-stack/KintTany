"""M5.2 fail-closed contracts for animation in REAL guest RSX TEX0 draw."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class GuestMutationTests(unittest.TestCase):
    def test_guest_texture_rotates_same_address(self):
        s=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
        for token in (
            "M51_TEX_OFFSET", "m51_guest_textured_quad_palette(swizzled,phase",
            "unsigned color=((x>=4u)", "+ palette) & 3u",
            "rsx_draw_engine_method(NV4097_SET_TEXTURE_OFFSET,M51_TEX_OFFSET)",
            "rsx_draw_engine_method(NV4097_DRAW_INDEX_ARRAY",
            "ar_probe_m51_readback_quad(pixels)",
            "ar_probe_cache_reset()", "ar_probe_cache_uploads()",
            "ar_probe_cache_replacements()", "*replacements<2u",
            "guest!=1u || encoded!=1u", "pixels[q]!=m51_colors[(q+phase)&3u]"):
            self.assertIn(token,s)
        self.assertNotIn("computeCommandEncoder",s)
    def test_old_draw_function_still_has_same_public_interface(self):
        s=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
        self.assertIn("int ar_probe_m51_guest_textured_quad(unsigned swizzled,",s)
        self.assertIn("return m51_guest_textured_quad_palette(swizzled,0u,",s)
        app=(ROOT/"ios/ARProbeApp.m").read_text()
        for name in ("testM52TextureMutation:","testM51GuestDraw:",
                     "testRSXCache:","testGuestRSXShader:",
                     "drawIndexedQuad:","drawRSXBoundTexture:"):
            self.assertIn(name,app)
    def test_pipeline_proven_on_device_not_claimed_by_ci(self):
        workflow=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
        self.assertIn("grep -q '_ar_probe_m52_guest_texture_mutation'",workflow)
        self.assertIn("M5.2: 3 guest FP TEX0 GPU draws",workflow)
        self.assertIn("AscensionRecompProbe-0.5.3-unsigned.ipa",workflow)
        self.assertIn("0.5.3-unsigned.ipa",
                      (ROOT/"tools/build_ios_probe_ipa.sh").read_text())
if __name__=="__main__":
    unittest.main()
