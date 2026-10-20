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
            source.write_text(
                '#include <stdint.h>\n'
                'extern "C" const char* ppu_vfs_root = ".";\n'
                'void host_path() {\n' + anchor + '\n}\n'
                'static void cellFsOpen(ppu_context* ctx)\n{\n}\n'
                '    ctx->gpr[3] = CELL_OK;\n}\n\n/* cellFsSdataOpen\n'
                'static void cellFsRead(ppu_context* ctx)\n{\n}\n'
                '    size_t n = fread(vm_base + buf, 1, (size_t)nbytes, g_files[fd]);'
                '   /* raw bytes, no swap */\n')

            MODULE.patch_ios_game_mount(upstream)
            result = source.read_text()
            self.assertIn("ASCENSION_IOS_NPUA80918_MOUNT", result)
            self.assertIn('"/dev_hdd0/game/NPUA80918"', result)
            self.assertIn('snprintf(out, cap, "%s/%s", ppu_vfs_root, tail)', result)
            self.assertIn("ps3_vfs_ps3game_fallback(out, cap)", result)
            self.assertIn("ascension_fs_open_calls", result)
            self.assertIn("ascension_fs_read_bytes.fetch_add", result)

            MODULE.patch_ios_game_mount(upstream)
            self.assertEqual(result, source.read_text())

    def test_runtime_holds_files_grant_and_binds_root_before_guest_entry(self):
        bridge = (ROOT / "ios" / "ARLivePPUBridge.c").read_text()
        self.assertIn("ARGameFolderBeginGuestSession(guest_root", bridge)
        self.assertIn("ar_m772_runtime_init((uint8_t*)ar_guest_memory_base(),", bridge)
        self.assertIn("ar_guest_memory_capacity(),guest_root", bridge)
        self.assertIn("ARGameFolderEndGuestSession();", bridge)

    def test_m772_full_lift_skips_legacy_aot_install_and_keeps_full_budget(self):
        bridge = (ROOT / "ios" / "ARLivePPUBridge.c").read_text()
        self.assertIn("#ifdef ASCENSION_PRIVATE_AOT_LINKED\n#if !defined(ASCENSION_M772_LINKED)", bridge)
        self.assertIn("#ifdef ASCENSION_M772_LINKED\n /* M7.72 dispatches the statically recompiled PS3Recomp function table.", bridge)
        self.assertIn("out[6]=(uint32_t)ar_run(&ctx,image.entry_code,32768u);", bridge)

    def test_m772_keeps_legacy_aot_symbols_for_binary_attestation_only(self):
        build = (ROOT / "tools" / "build_ios_probe_ipa.sh").read_text()
        self.assertIn("LEGACY_AOT_KEEP_SYMBOLS=(", build)
        self.assertIn('LEGACY_AOT_KEEP_FLAGS+=("-Wl,-u,_${symbol}")', build)
        self.assertIn("ar_m762_register_discovered", build)
        self.assertIn("ar_m769_register_frontier", build)


if __name__ == "__main__":
    unittest.main()
