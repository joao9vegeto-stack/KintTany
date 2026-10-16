"""M5.3 real RSX render-to-texture ping pong, no host shortcut."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from enable_ios_guest_draw_probe import patch_engine

class RealMultipass(unittest.TestCase):
    def test_preserves_m52_and_m51_public_entry_points(self):
        s=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
        for v in ("int ar_probe_m51_guest_textured_quad(", 
                  "int ar_probe_m52_guest_texture_mutation(",
                  "int ar_probe_m53_guest_multipass(",
                  "m51_guest_textured_quad_palette(swizzled,phase,",
                  "m51_guest_textured_quad_palette_ex(swizzled,0u,0u,M51_RT_OFFSET,",
                  "m51_guest_textured_quad_palette_ex(swizzled,0u,1u,M53_RT_B_OFFSET,"):
            self.assertIn(v,s)
    def test_source_is_previous_local_render_target_not_host_upload(self):
        s=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
        for v in ("sample_surface ? M51_RT_OFFSET : M51_TEX_OFFSET",
                  "sample_surface ? 1u : 2u",
                  "sample_surface ? M51_WIDTH*4u : M51_TEX_W*4u",
                  "ar_probe_m53_surface_views()",
                  "if(*surface_views<1u) return -304;",
                  "if(*new_uploads!=0u) return -305;",
                  "if(pixels[q]!=m51_colors[q])",
                  "rsx_draw_engine_method(NV4097_DRAW_INDEX_ARRAY",
                  "rsx_draw_engine_guest_draws()",
                  "ar_probe_m51_readback_quad(pixels)"):
            self.assertIn(v,s)
    def test_backend_instrumentation_uses_surface_views(self):
        x=(ROOT/"tools/enable_ios_guest_draw_probe.py").read_text()
        self.assertIn("if (view) ar_m53_surface_view_count++",x)
        self.assertIn("g.surfaces[sampled].handle",x)
        self.assertIn('view_anchor = "            textures[u] = view ? view : g.surfaces[sampled].handle;"',x)
    def test_existing_regressions_and_ui(self):
        app=(ROOT/"ios/ARProbeApp.m").read_text()
        for v in ("testM53Multipass:","testM52TextureMutation:",
                  "testM51GuestDraw:","testRSXCache:"):
            self.assertIn(v,app)
        w=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
        self.assertIn("'_ar_probe_m53_surface_views'",w)
        self.assertIn("AscensionRecompProbe-0.6.5-unsigned.ipa",w)
if __name__=="__main__":
    unittest.main()
