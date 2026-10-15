"""Synthetic-only geometry pipeline regression coverage."""
import unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]
class TestRSXTriangle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=(root/'ios/ARRSXMethodProbe.c').read_text()
        cls.app=(root/'ios/ARProbeApp.m').read_text()
    def test_uses_inline_guest_nv4097_not_metal_triangle(self):
        for x in ('NV4097_SET_BEGIN_END','RSX_PRIMITIVE_TRIANGLES',
                  '0x1818u','rsx_draw_engine_readback_center',
                  'rsx_draw_engine_method(0xe944u,0u)'):
            self.assertIn(x,self.c)
        self.assertNotIn('newRenderPipelineState',self.c)
        self.assertNotIn('MTLRenderPassDescriptor',self.c)
    def test_fail_closed_geometry(self):
        self.assertIn('if(pixel==bg) return -13',self.c)
        self.assertIn('return -14',self.c)
        self.assertIn('if(!rsx_draw_engine_enabled())',self.c)
    def test_preserves_existing_clear_taps(self):
        self.assertIn('ar_probe_rsx_clear_flip',self.app)
        self.assertIn('drawTriangle:',self.app)
        self.assertIn('referenceOK=',self.app)
