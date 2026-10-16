"""M5.4.1 regression for on-device -424 / depth counter 0.
The depth register was correctly ENABLED, then UNCONDITIONALLY
DISABLED between the surface configuration and DRAW_INDEX_ARRAY.
The source ordering guard is intentionally strict, including the
old M5.1-M5.3 behavior when depth_mode==0. """
import re
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/"ios/ARGuestDrawProbe.c").read_text()

class NoDepthOverride(unittest.TestCase):
    def test_guest_depth_enabled_until_draw(self):
        start=SRC.index("static int m51_guest_textured_quad_palette_ex(")
        end=SRC.index("static int m51_guest_textured_quad_palette(",start)
        f=SRC[start:end]
        begin=f.index("rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,1u);")
        finish=f.index("rsx_draw_engine_method(NV4097_DRAW_INDEX_ARRAY,")
        self.assertLess(begin,finish)
        path=f[begin:finish]
        self.assertEqual(path.count("NV4097_SET_DEPTH_TEST_ENABLE,0u"),2)
        # Exactly two conditional disable paths: stencil-only and legacy.
        self.assertRegex(path,r"if\(depth_mode>=3u\)\s*\{[\s\S]*?NV4097_SET_DEPTH_TEST_ENABLE,0u")
        self.assertIn("if (!depth_mode)",path)
        self.assertRegex(path,r"if \(!depth_mode\)\s*rsx_draw_engine_method\(NV4097_SET_DEPTH_TEST_ENABLE,0u\)")
        self.assertNotIn("    rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,0u);",path.splitlines())
    def test_legacy_path_still_disables_depth(self):
        self.assertIn("if (!depth_mode)\n        rsx_draw_engine_method(NV4097_SET_DEPTH_TEST_ENABLE,0u);",SRC)
        self.assertIn("0.0f,0u,pixels,encoded,guest_draws,shader_state",SRC)
        self.assertIn("0.0f,0u,pixels,&encoded,&guest,shader",SRC)
    def test_m54_pass2_preserves_depth(self):
        for needle in ("const unsigned expected[3]={0u,0u,2u}",
          "depth_mode==0u || depth_mode==1u ||",
          "depth_mode==3u || depth_mode==6u",
          "NV4097_SET_SURFACE_ZETA_OFFSET,M54_Z_OFFSET",
          "NV4097_SET_DEPTH_FUNC,0x0201u",
          "if(*depth_draws!=3u) return -440"):
            self.assertIn(needle,SRC)
if __name__=="__main__":unittest.main()
