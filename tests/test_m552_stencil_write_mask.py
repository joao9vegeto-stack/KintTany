"""M5.5.2 physical iPhone -528 regression: the stencil bit MUST be
written by guest RSX before trying to compare ref1 on the third draw.
"""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
OVER=(ROOT/"tools/enable_ios_guest_draw_probe.py").read_text()
class StencilMaskFix(unittest.TestCase):
    def test_actual_write_mask_register_precedes_guest_draw(self):
        f=SRC[SRC.index("static int m51_guest_textured_quad_palette_ex("):
              SRC.index("static int m51_guest_textured_quad_palette(")]
        mask=f.index("rsx_draw_engine_method(M55_NV4097_SET_STENCIL_MASK,write_mask)")
        op=f.index("rsx_draw_engine_method(NV4097_SET_STENCIL_OP_ZPASS,")
        draw=f.index("rsx_draw_engine_method(NV4097_DRAW_INDEX_ARRAY")
        self.assertTrue(mask<op<draw)
        self.assertIn("#define M55_NV4097_SET_STENCIL_MASK 0x0000032Cu",SRC)
        self.assertIn("always ? 0x1e01u : 0x1e00u",f)
        self.assertIn("uint32_t write_mask=0xffu, read_mask=0xffu",f)
        self.assertIn("unsigned always=(depth_mode==3u)",f)
    def test_native_metal_counter_requires_actual_mask(self):
        self.assertIn("rs->s_write_mask == 0xffu",OVER)
        self.assertIn("p->ar_m55_stencil",OVER)
        self.assertIn("r->depth && eng_obj(r->depth)",OVER)
    def test_failure_path_publishes_observed_stencil_draws(self):
        f=SRC[SRC.index("int ar_probe_m55_guest_stencil_mask("):]
        obs=f.index("*stencil_draws=ar_probe_m55_stencil_draws();",
                  f.index("*guest_total+=guest"))
        fail=f.index("if(guest!=1u||encoded!=1u)")
        pix=f.index("if(pixels[q]!=m51_colors[(q+expected[i])&3u])")
        self.assertTrue(obs<fail<pix)
    def test_no_legacy_depth_or_stencil_regression(self):
        self.assertIn("ar_probe_m54_guest_depth_occlusion(",SRC)
        self.assertIn("ar_probe_m53_guest_multipass(",SRC)
        self.assertIn("if (!depth_mode)",SRC)
        self.assertIn("rsx_draw_engine_method(NV4097_SET_STENCIL_TEST_ENABLE,0u)",SRC)
if __name__=="__main__":unittest.main()
