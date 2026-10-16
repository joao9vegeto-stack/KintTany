"""M5.0: exact native guest shader path, source-gated and versioned."""
import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from enable_ios_guest_shaders import patch

class M50NativeGuestShaderTest(unittest.TestCase):
    def test_fail_closed_if_upstream_changed(self):
        with self.assertRaises(ValueError):
            patch("not upstream", "not translator")
    def test_patching_changes_only_ios_translation(self):
        base='if(UNIX AND NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")\n'+(
            '# Guest shaders on Vulkan: HLSL -> SPIR-V. glslang only -- Vulkan consumes\n')
        src='spvc_compiler_options_set_uint(opt, SPVC_COMPILER_OPTION_MSL_PLATFORM, SPVC_MSL_PLATFORM_MACOS);'
        cmake, cpp=patch(base, src)
        self.assertIn('PS3RECOMP_HAVE_MSL_TRANSLATION=1', cmake)
        self.assertIn('glslang::SPIRV spirv-cross-c',cmake)
        self.assertIn('"${AR_SHADER_DEPS}" "${AR_SHADER_DEPS}/SPIRV-Cross"',cmake)
        # Ensure these are actual CMake lines, not escaped \\n inside a comment.
        self.assertIn('    target_include_directories(ps3recomp_runtime PRIVATE\n',cmake)
        self.assertNotIn('\\n    target_include_directories',cmake)
        self.assertIn('SPVC_MSL_PLATFORM_IOS',cpp)
        self.assertIn('SPVC_MSL_PLATFORM_MACOS',cpp)
    def test_real_microcode_to_shader_not_fixed_substitute(self):
        c=(ROOT/'ios/ARShaderProbe.m').read_text()
        for symbol in ('rsx_vp_decompile(vp','rsx_fp_decompile_buffered_ex(fp',
                       'rsx_test_fp_tex_r0_tc0(fp','rsx_hlsl_to_msl(hlsl',
                       'newLibraryWithSource:source','newFunctionWithName:@"main0"',
                       '[[texture(0)]]','[[sampler(0)]]','if (rc) return rc'):
            self.assertIn(symbol, c)
    def test_old_fixed_fallback_preserved_even_with_real_translator(self):
        overlay=(ROOT/'tools/enable_ios_fixed_pipeline.py').read_text()
        self.assertIn('const int fixed_pair=',overlay)
        self.assertIn('if(!s_guest_shaders&&!fixed_pair)return 0',overlay)
        self.assertNotIn('const int fixed_pair=!s_guest_shaders',overlay)
    def test_ipa_remains_diagnostic_and_traceable(self):
        wf=(ROOT/'.github/workflows/ascension-recomp-m0.yml').read_text()
        app=(ROOT/'ios/ARProbeApp.m').read_text()
        sh=(ROOT/'tools/build_ios_probe_ipa.sh').read_text()
        for token in ('M5.0','enable_ios_guest_shaders.py','test_shader_msl',
                      'ps3recomp_boot_smoke','m50-guest-shaders.log'):
            self.assertIn(token,wf)
        self.assertIn('ar_probe_guest_shader_compile', app)
        self.assertIn('ARShaderProbe.m', sh)
        self.assertIn('0.6.11-unsigned.ipa', sh)
        self.assertIn("grep -F '_rsx_hlsl_to_msl_available'",wf)
        self.assertNotIn("| grep -q '_rsx_hlsl_to_msl_available'",wf)

if __name__ == '__main__':
    unittest.main()
