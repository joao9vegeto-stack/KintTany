"""Static regression checks for real RSX texture format conversion and GPU sampling."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TextureProbe(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.s=(ROOT/"ios/ARTextureProbe.m").read_text()
  cls.app=(ROOT/"ios/ARProbeApp.m").read_text()
 def test_real_rsx_decoder_both_layouts(self):
  for word in ("rsx_texture_layout_pitched","rsx_texture_decode",
    "rsx_swizzle_offset","swizzled?0x85u:0xA5u","p[0]=c[3]",
    "layout.swizzled","memcmp(decoded"):
   self.assertIn(word,self.s)
 def test_real_fragment_sampling_and_readback(self):
  for word in ("texture2d<float> tex [[texture(0)]]","tex.sample(s,v.uv)",
    "newRenderPipelineStateWithDescriptor","drawPrimitives:",
    "getBytes:rgba","seen!=0x0fu","presentDrawable:drawable"):
   self.assertIn(word,self.s)
 def test_fail_closed_and_prior_controls(self):
  self.assertIn("return -53",self.s)
  for word in ("drawTriangle:","drawDMATriangle:","drawIndexedQuad:",
               "drawPS3Texture:","fourTap.numberOfTapsRequired=4"):
   self.assertIn(word,self.app)
