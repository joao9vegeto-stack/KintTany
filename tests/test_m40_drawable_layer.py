"""Synthetic host patch tests: no commercial PS3 inputs."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from enable_ios_drawable_layer import patch_metal,patch_public_header
VIEW=(Path(__file__).resolve().parents[1]/"ios/ARMetalView.m").read_text()
class LayerPatchTests(unittest.TestCase):
 def test_backend_iOS_window_path(self):
  template='''static CAMetalLayer*       s_layer;      /* windowed only   */
static u32                 s_height = 720;
static u32                 s_width = 1280;
static int create_depth(void)
{
    MTLTextureDescriptor* td =
        [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTL_DEPTH_FORMAT
                                                           width:s_width
                                                          height:s_height
                                                       mipmapped:NO];
}
int rsx_metal_backend_init(u32 width, u32 height, const char* title)
{
#if TARGET_OS_IPHONE
        s_headless = 1;
        rc = create_offscreen();
#else
        rc = create_window(title);
#endif
}
static void mtl_set_render_target(u32 w, u32 h)
{
    s_width = w; s_height = h;
    if (s_layer) s_layer.drawableSize = CGSizeMake((CGFloat)w, (CGFloat)h);
}
'''
  s=patch_metal(template)
  self.assertIn('rsx_metal_backend_set_ios_layer',s)
  self.assertIn('rsx_metal_backend_set_ios_output_scale',s)
  self.assertIn('depth_width',s)
  self.assertIn('if (s_ready || !(scale >= 0.5f && scale <= 1.0f)) return -1;',s)
  self.assertIn('s_headless = 0',s)
  self.assertIn('s_layer = s_ios_layer',s)
  self.assertIn('rc = create_offscreen()',s)
 def test_header_declaration(self):
  template='int  rsx_metal_backend_init(u32 width, u32 height, const char* title);'
  s=patch_public_header(template)
  self.assertIn('rsx_metal_backend_set_ios_layer',s)
  self.assertIn('rsx_metal_backend_set_ios_output_scale',s)
  self.assertEqual(patch_public_header(s),s)
 def test_missing_branch_fails(self):
  with self.assertRaises(ValueError):patch_metal('static CAMetalLayer* s_layer;')
 def test_rotation_does_not_override_guest_drawable_size(self):
  self.assertIn('if (self.ps3BackendBound) return;',VIEW)
  self.assertIn('self.ps3BackendBound=',VIEW)
