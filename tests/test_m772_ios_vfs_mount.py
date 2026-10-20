import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "m772_build_ios", ROOT / "tools" / "m772_build_ios.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M772IOSVfsMountTests(unittest.TestCase):
    def test_patch_maps_installed_title_to_selected_game_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            upstream = pathlib.Path(tmp)
            source = upstream / "runtime" / "ppu" / "ppu_fs.cpp"
            source.parent.mkdir(parents=True)
            anchor = '    static const char* hdd0_root = nullptr; static int hdd0_init = 0;'
            source.write_text(anchor + "\n")

            MODULE.patch_ios_game_mount(upstream)
            result = source.read_text()
            self.assertIn("ASCENSION_IOS_NPUA80918_MOUNT", result)
            self.assertIn('"/dev_hdd0/game/NPUA80918"', result)
            self.assertIn('snprintf(out, cap, "%s/%s", ppu_vfs_root, tail)', result)
            self.assertIn("ps3_vfs_ps3game_fallback(out, cap)", result)

            MODULE.patch_ios_game_mount(upstream)
            self.assertEqual(result, source.read_text())

    def test_runtime_holds_files_grant_and_binds_root_before_guest_entry(self):
        bridge = (ROOT / "ios" / "ARLivePPUBridge.c").read_text()
        self.assertIn("ARGameFolderBeginGuestSession(guest_root", bridge)
        self.assertIn("ar_m772_runtime_init((uint8_t*)ar_guest_memory_base(),", bridge)
        self.assertIn("ar_guest_memory_capacity(),guest_root", bridge)
        self.assertIn("ARGameFolderEndGuestSession();", bridge)


if __name__ == "__main__":
    unittest.main()
