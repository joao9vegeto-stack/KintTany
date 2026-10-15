"""Checks DMA geometry test preserves inline/M4.5 path and bounds safety."""
import unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]
class DMATests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.g=(root/'ios/ARRSXMethodProbe.c').read_text()
  cls.a=(root/'ios/ARProbeApp.m').read_text()
 def test_genuine_guest_memory_fetch(self):
  for k in ('NV4097_SET_VERTEX_DATA_ARRAY_OFFSET','NV4097_DRAW_ARRAYS',
           'rsx_draw_engine_set_guest_memory','ar_write_be_float',
           'RSX_LOCATION_MAIN','(uint64_t)offset + bytes > ppu_vm_size',
           'ar_probe_rsx_dma_triangle'):
   self.assertIn(k,self.g)
 def test_no_regression_inline_and_clear(self):
  self.assertIn('ar_probe_rsx_clear_flip',self.g)
  self.assertIn('ar_probe_rsx_triangle',self.g)
  self.assertIn('drawTriangle:',self.a)
  self.assertIn('drawDMATriangle:',self.a)
 def test_guard_guest_buffer(self):
  self.assertIn('AR_DMA_VERTEX_OFFSET+AR_DMA_VERTEX_BYTES',self.g)
  self.assertIn('if(pixel==bg) return -23',self.g)
  self.assertIn('return -24',self.g)
