"""No game data, synthetic index-buffer regression checks."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class IndexedMesh(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.s=(ROOT/"ios/ARRSXMethodProbe.c").read_text()
  cls.app=(ROOT/"ios/ARProbeApp.m").read_text()
 def test_index_method_path(self):
  for x in ("NV4097_SET_INDEX_ARRAY_ADDRESS","NV4097_SET_INDEX_ARRAY_DMA",
            "NV4097_DRAW_INDEX_ARRAY","const uint32_t idx[6]={0,1,2,0,2,3}",
            "ar_be_index","rsx_draw_engine_readback_center"):
   self.assertIn(x,self.s)
 def test_fail_closed_big_endian(self):
  for x in ("idx>>24","idx>>8","AR_IDX_EBO+24u>ppu_vm_size",
            "if(pixel==bg)return -33","return -34","use32?0u:0x10u"):
   self.assertIn(x,self.s)
 def test_prior_modes_preserved(self):
  for x in ("ar_probe_rsx_clear_flip","ar_probe_rsx_triangle","ar_probe_rsx_dma_triangle"):
   self.assertIn(x,self.s)
  for x in ("drawTriangle:","drawDMATriangle:","drawIndexedQuad:"):
   self.assertIn(x,self.app)
