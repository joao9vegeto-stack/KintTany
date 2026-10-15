"""Synthetic host patch tests: no commercial PS3 inputs."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from enable_ios_drawable_layer import patch_metal,patch_public_header
class LayerPatchTests(unittest.TestCase):
 def test_backend_iOS_window_path(self):
  template='''static CAMetalLayer*       s_layer;      /* windowed only   */
int rsx_metal_backend_init(u32 width, u32 height, const char* title)
{
#if TARGET_OS_IPHONE
        s_headless = 1;
        rc = create_offscreen();
#else
        rc = create_window(title);
#endif
}
'''
  s=patch_metal(template)
  self.assertIn('rsx_metal_backend_set_ios_layer',s)
  self.assertIn('s_headless = 0',s)
  self.assertIn('s_layer = s_ios_layer',s)
  self.assertIn('rc = create_offscreen()',s)
 def test_header_declaration(self):
  s=patch_public_header('int  rsx_metal_backend_init(u32 width, u32 height, const char* title);')
  self.assertIn('rsx_metal_backend_set_ios_layer',s)
 def test_missing_branch_fails(self):
  with self.assertRaises(ValueError):patch_metal('static CAMetalLayer* s_layer;')
