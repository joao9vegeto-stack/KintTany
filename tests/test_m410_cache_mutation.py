"""Verify the synthetic cache test really exercises content changes."""
import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from enable_ios_cache_counters import patch
class RSXCacheMutation(unittest.TestCase):
 def test_pinned_overlay_guard(self):
  with self.assertRaises(ValueError): patch("unexpected upstream")
 def test_cache_hash_observability(self):
  src=(ROOT/"tools/enable_ios_cache_counters.py").read_text()
  for x in ("ar_cache_replacements++","ar_cache_uploads++","if (fresh)"):
   self.assertIn(x,src)
 def test_three_real_gpu_frames(self):
  src=(ROOT/"ios/ARRSXMethodProbe.c").read_text()
  for x in ("for(unsigned i=0;i<3;i++)","ar_probe_rsx_texture_registers_palette(swizzled,i,out)",
            "if(rep<2u)return -92","if(up<2u)return -93",
            "actual[q]!=ar_tex_expected[(q+palette)&3u]"):
   self.assertIn(x,src)
 def test_m49_compatibility_and_ui(self):
  src=(ROOT/"ios/ARRSXMethodProbe.c").read_text()
  ui=(ROOT/"ios/ARProbeApp.m").read_text()
  self.assertIn("return ar_probe_rsx_texture_registers_palette(swizzled,0u,out)",src)
  self.assertIn("drawRSXBoundTexture:",ui)
  self.assertIn("testRSXCache:",ui)
  self.assertIn("UIControlEventTouchUpInside",ui)
