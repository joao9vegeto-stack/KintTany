"""M5.1 guards: guest VP+FP are used in a real NV4097 indexed draw."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from enable_ios_guest_draw_probe import patch_engine,patch_metal

class M51RealDrawTest(unittest.TestCase):
    def test_fail_closed_on_upstream_change(self):
        with self.assertRaises(ValueError): patch_engine("stale source")
        with self.assertRaises(ValueError): patch_metal("stale source")
    def test_guest_program_is_genuine_not_msl_substitution(self):
        s=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
        for token in (
            "rsx_test_vp_mov_out(vp,0", "rsx_test_vp_mov_out(vp+16,8",
            "rsx_test_fp_tex_r0_tc0(fp,0)", "NV4097_SET_TRANSFORM_PROGRAM",
            "NV4097_SET_SHADER_PROGRAM,M51_FP_OFFSET|2u",
            "NV4097_SET_VERTEX_DATA_ARRAY_OFFSET+8u*4u",
            "NV4097_SET_TRANSFORM_PROGRAM+(i&3u)*4u", "NV4097_DRAW_INDEX_ARRAY", "rsx_draw_engine_guest_draws()",
            "ar_probe_m51_encoded_draws()", "ar_probe_m51_readback_quad(pixels)",
            "ar_probe_m51_shader_state(shader_state)", "m51_cleanup();", "found==15u"):
            self.assertIn(token,s)
        self.assertNotIn("newLibraryWithSource",s)
    def test_instrumentation_reads_real_guest_render_target(self):
        s=(ROOT/"tools/enable_ios_guest_draw_probe.py").read_text()
        for token in ("g.last_present_surface","g.be->readback",
                      "strstr(ps_hlsl, \"rsx_tex[0].Sample(\")",
                      "r->tex[0] && eng_obj(r->tex[0])",
                      "ar_m51_draws_encoded++"):
            self.assertIn(token,s)
        self.assertNotIn("computeCommandEncoder",s)
    def test_old_probe_and_ipa_are_preserved(self):
        app=(ROOT/"ios/ARProbeApp.m").read_text()
        for token in ("testGuestRSXShader:","testRSXCache:","drawTriangle:",
                      "drawDMATriangle:","drawIndexedQuad:",
                      "drawPS3Texture:","drawRSXBoundTexture:"):
            self.assertIn(token,app)
        self.assertIn("testM51GuestDraw:",app)
        self.assertIn("0.5.4-unsigned.ipa",(ROOT/"tools/build_ios_probe_ipa.sh").read_text())
