import unittest,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools'))
from enable_ios_fixed_pipeline import edit
class Tests(unittest.TestCase):
 def test_backend_rejects_unexpected_source(self):
  with self.assertRaises(ValueError): edit('no upstream backend','')
 def test_fixed_shader_source_abi(self):
  s=(root/'ios/ARFixedFallback.metal').read_text()
  for token in ('a0 [[attribute(0)]]','a3 [[attribute(3)]]','float4 vp_c[512]','vp_posscale','vp_posoffset','[[buffer(0)]]'):
   self.assertIn(token,s)
 def test_exact_title_shader_fail_closed(self):
  script=(root/'tools/enable_ios_fixed_pipeline.py').read_text()
  self.assertIn('if(!s_guest_shaders&&!fixed_pair)return 0',script)
  self.assertIn('Out.col0 = input.a3;',script)
