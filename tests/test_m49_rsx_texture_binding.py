"""Synthetic texture-binding bridge regression tests."""
import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from enable_ios_rsx_texture_debug import patch
class ProbeContract(unittest.TestCase):
 def test_pinned_fail_closed(self):
  with self.assertRaises(ValueError): patch("not an RSX Metal backend")
 def test_old_and_current_draw_guards(self):
  for guard in ("    if (!p->pso) return;",
                "    if (!p->pso) { s_eng_encoding_failed = 1; return; }"):
   source=("static void eng_bind_textures(void* user, const u32* textures,\n"
     "static void eng_encode_draw(id<MTLRenderCommandEncoder> enc, const EngRecord* r,\n"
     +guard+"\n")
   self.assertIn("if(r->tex[0]) ar_probe_draw_tex0=r->tex[0];", patch(source))
 def test_register_to_real_draw_to_gpu(self):
  g=(ROOT/"ios/ARRSXMethodProbe.c").read_text()
  app=(ROOT/"ios/ARProbeApp.m").read_text()
  for key in ("NV4097_SET_TEXTURE_OFFSET","NV4097_SET_TEXTURE_FORMAT",
    "NV4097_SET_TEXTURE_CONTROL0","NV4097_SET_TEXTURE_CONTROL1",
    "NV4097_SET_TEXTURE_FILTER","NV4097_SET_TEXTURE_IMAGE_RECT",
    "NV4097_SET_TEXTURE_CONTROL3","rsx_swizzle_offset",
    "rsx_draw_engine_flush","rsx_metal_backend_debug_sample_texture0"):
   self.assertIn(key,g)
  self.assertIn("drawRSXBoundTexture:",app)
  self.assertIn("fiveTap.numberOfTapsRequired=5",app)
 def test_bound_draw_resource_not_faked(self):
  p=(ROOT/"tools/enable_ios_rsx_texture_debug.py").read_text()
  self.assertIn("r->tex[0]",p)
  self.assertIn("eng_obj(ar_probe_draw_tex0)",p)
  self.assertIn("texture2d<float,access::sample>",p)
  self.assertIn("t.sample(s,uv)",p)
 def test_previous_probes_preserved(self):
  app=(ROOT/"ios/ARProbeApp.m").read_text()
  for x in ("drawTriangle:","drawDMATriangle:","drawIndexedQuad:",
            "drawPS3Texture:"):
   self.assertIn(x,app)
