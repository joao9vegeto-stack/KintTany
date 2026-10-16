"""Fail-closed regression checks for the CI-only headless boot smoke."""
import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from enable_macos_boot_smoke_null_backend import patch

class CIHeadlessBoot(unittest.TestCase):
    def test_refuse_unpinned_source(self):
        with self.assertRaises(ValueError):
            patch('wrong','wrong')
    def test_select_only_host_boot_test(self):
        cmake='        target_link_libraries(ps3recomp_boot_smoke PRIVATE ps3recomp_runtime)'
        boot='#elif defined(__APPLE__)\nextern "C" int  rsx_metal_backend_init'
        cmake2,boot2=patch(cmake,boot)
        self.assertIn('target_compile_definitions(ps3recomp_boot_smoke PRIVATE',cmake2)
        self.assertIn('ASCENSIONRECOMP_BOOT_SMOKE_NULL_RSX',cmake2)
        self.assertIn('!defined(ASCENSIONRECOMP_BOOT_SMOKE_NULL_RSX)',boot2)
        self.assertIn('rsx_metal_backend_init',boot2)
    def test_workflow_patch_and_regression(self):
        w=(ROOT/'.github/workflows/ascension-recomp-m0.yml').read_text()
        self.assertIn('python3 tools/enable_macos_boot_smoke_null_backend.py upstream',w)
        self.assertIn('./build/ps3recomp_boot_smoke build/smoke/smoke.elf',w)
        self.assertIn('python3 tools/enable_ios_guest_shaders.py upstream',w)
        self.assertIn('AscensionRecompProbe-0.6.0-unsigned.ipa',w)

if __name__=='__main__':
    unittest.main()
