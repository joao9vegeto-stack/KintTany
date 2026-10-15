"""Structural regression tests for synthetic PS3 register path.

Does not claim GPU validation until the iPhone renders the colored RSX frame.
"""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RSXMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'ios'/'ARRSXMethodProbe.c').read_text()
    def test_guest_registers_not_direct_metal(self):
        for required in ('NV4097_SET_COLOR_CLEAR_VALUE','NV4097_CLEAR_SURFACE',
                         'NV4097_SET_SURFACE_COLOR_AOFFSET',
                         'rsx_draw_engine_method(0xE944u, 0u)',
                         'rsx_draw_engine_readback_center()'):
            self.assertIn(required,self.source)
        self.assertNotIn('MTLRenderPassDescriptor',self.source)
        self.assertNotIn('presentDrawable',self.source)
    def test_fails_on_invalid_path_or_pixel(self):
        self.assertIn('return -1',self.source)
        self.assertIn('return -2',self.source)
        self.assertIn('return -3',self.source)
        self.assertIn('if(pixel!=argb)',self.source)
    def test_uses_local_rsx_surface(self):
        self.assertIn('CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER',self.source)
        self.assertIn('RSX_LOCATION_LOCAL',self.source)
        self.assertIn('AR_WIDTH * 4u',self.source)
