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
    def test_live_hle_dispatch_requires_generated_table_and_tracks_unresolved_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            upstream = pathlib.Path(tmp)
            hle = upstream / "runtime" / "ppu" / "ppu_hle.cpp"
            loader = upstream / "runtime" / "ppu" / "ppu_loader.cpp"
            hle.parent.mkdir(parents=True)
            hle.write_text('''/* Populated by the generated registration unit (gen_hle_nids.py). Weak so a
 * build without it still links (no HLE registered -> imports log + return 0). */
extern "C" void ppu_hle_register_all(void) __attribute__((weak));
extern "C" void ppu_hle_register_all(void) {}
extern "C" void ppu_hle_init(void) { ppu_hle_register_all(); }
extern "C" void ps3_hle_call(uint32_t nid, ppu_context* ctx)
{
    ps3_nid_entry* e = nullptr;
    if (!e || !e->handler) {
        ps3_msf("hle:unresolved:0x%08X", nid);
        return;
    }
}
''')
            loader.write_text('''extern "C" void lv2_syscall(ppu_context* ctx)
{
}
''')

            MODULE.patch_m772_live_dispatch(upstream)
            result = hle.read_text()
            self.assertIn("ASCENSION_M772_STRONG_HLE_REGISTRATION", result)
            self.assertNotIn(
                'extern "C" void ppu_hle_register_all(void) __attribute__((weak));',
                result)
            self.assertIn("ASCENSION_M775_LIVE_HLE_TELEMETRY", result)
            branch = result.split("if (!e || !e->handler) {", 1)[1]
            self.assertIn("ASCENSION_M775_UNRESOLVED_HLE_TELEMETRY", branch)
            self.assertIn("ar_m772_note_unresolved_hle(nid, (uint32_t)ctx->lr, ctx);", branch)
            self.assertIn("ASCENSION_M775_LIVE_SYSCALL_TELEMETRY", loader.read_text())

            once = result
            MODULE.patch_m772_live_dispatch(upstream)
            self.assertEqual(once, hle.read_text())

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
            self.assertIn('"/app_home", "app_home", "e:/app_home"', result)
            self.assertIn('"%s/USRDIR/%s", ppu_vfs_root, app_home_tail', result)
            self.assertIn("ps3_vfs_ps3game_fallback(out, cap)", result)
            self.assertIn("ascension_fs_open_calls", result)
            self.assertIn("ascension_fs_read_bytes.fetch_add", result)

            MODULE.patch_ios_game_mount(upstream)
            self.assertEqual(result, source.read_text())

    def test_changed_vfs_translation_invalidates_old_m772_archive(self):
        build = (ROOT / "tools" / "build_ios_probe_ipa.sh").read_text()
        workflow = (ROOT / ".github" / "workflows" / "ascension-recomp-m0.yml").read_text()
        attestation = (ROOT / "tools" / "m772_build_ios.py").read_text()
        patch = "npua80918-and-app-home-usrdir-v1"
        self.assertIn("a['ios_vfs_mount_patch']=='" + patch + "'", build)
        self.assertIn("a['ios_vfs_mount_patch']=='" + patch + "'", workflow)
        self.assertIn('"ios_vfs_mount_patch": "' + patch + '"', attestation)

    def test_unaligned_guest_vm_patch_covers_both_pointer_narrowing_forms(self):
        build = (ROOT / "tools" / "m772_build_ios.py").read_text()
        shell = (ROOT / "tools" / "build_ios_probe_ipa.sh").read_text()
        workflow = (ROOT / ".github" / "workflows" / "ascension-recomp-m0.yml").read_text()
        bridge = (ROOT / "runtime" / "ppu_bridge.c").read_text()
        self.assertIn('r"\\(uint32_t\\)\\s*\\(uintptr_t\\)', build)
        self.assertIn('r"\\(u32\\)\\s*\\(uintptr_t\\)', build)
        self.assertIn("pointer_patch_count != 380", build)
        self.assertIn("helper_uses != 382", build)
        self.assertIn("value - base < (uintptr_t)ppu_vm_size", build)
        self.assertIn("value <= UINT32_MAX", build)
        self.assertIn("return UINT32_MAX", build)
        self.assertIn("mach-anywhere-4g-relative-guest-ea-v1", build)
        self.assertIn("mach-anywhere-4g-relative-guest-ea-v1", shell)
        self.assertIn("mach-anywhere-4g-relative-guest-ea-v1", workflow)
        self.assertIn("VM_FLAGS_ANYWHERE", bridge)
        self.assertNotIn("VM_FLAGS_FIXED", bridge)
        self.assertIn("vm_allocate(mach_task_self()", bridge)
        self.assertNotIn("mach_vm.h", bridge)
        self.assertIn("(vm_size_t)AR_M772_VM_GUEST,VM_FLAGS_ANYWHERE", bridge)
        self.assertIn("mmap(NULL,AR_M772_VM_GUEST", bridge)
        self.assertIn("PROT_READ|PROT_WRITE", bridge)
        self.assertNotIn("vm_protect(", bridge)
        self.assertNotIn("mprotect(", bridge)

    def test_runtime_holds_files_grant_and_binds_root_before_guest_entry(self):
        bridge = (ROOT / "ios" / "ARLivePPUBridge.c").read_text()
        self.assertIn("ARGameFolderBeginGuestSession(guest_root", bridge)
        self.assertIn("ar_m772_runtime_init((uint8_t*)ar_guest_memory_base(),", bridge)
        self.assertIn("ar_guest_memory_capacity(),guest_root", bridge)
        self.assertIn("ARGameFolderEndGuestSession();", bridge)

    def test_m772_full_lift_skips_legacy_aot_install_and_keeps_full_budget(self):
        bridge = (ROOT / "ios" / "ARLivePPUBridge.c").read_text()
        self.assertIn("#ifdef ASCENSION_PRIVATE_AOT_LINKED\n#if !defined(ASCENSION_M772_LINKED)", bridge)
        self.assertIn("out[6]=(uint32_t)ar_m772_run_entry(&ctx,image.entry_code);", bridge)
        self.assertIn("ar_run() is reserved for legacy PPC", bridge)
        self.assertIn("fragments and would misread the entry function's saved LR", bridge)
        build = (ROOT / "tools" / "build_ios_probe_ipa.sh").read_text()
        self.assertIn("_ar_m772_runtime_begin", build)
        self.assertIn("_ar_m772_note_function", build)

    def test_m772_keeps_legacy_aot_symbols_for_binary_attestation_only(self):
        build = (ROOT / "tools" / "build_ios_probe_ipa.sh").read_text()
        self.assertIn("LEGACY_AOT_KEEP_SYMBOLS=(", build)
        self.assertIn('LEGACY_AOT_KEEP_FLAGS+=("-Wl,-u,_${symbol}")', build)
        self.assertIn("ar_m762_register_discovered", build)
        self.assertIn("ar_m769_register_frontier", build)
        self.assertIn("ar_m769_get_stats", build)
        self.assertIn("ar_m770_delta_install_sha256", build)

    def test_runtime_report_shows_live_m772_counters_before_historical_data(self):
        app = (ROOT / "ios" / "ARProbeApp.m").read_text()
        stage = (ROOT / "tools" / "m772_unpack_ci.py").read_text()
        self.assertIn("ar_m772_runtime_attest(m772)", app)
        self.assertIn("Chamadas de função AOT=%@", app)
        self.assertIn("último PC=0x%08llX", app)
        self.assertIn("native_aot_function_entry_hooks", stage)
        self.assertIn("ar_m772_note_function", stage)
        self.assertNotIn("Agora: 13252 AOT", app)

    def test_each_elf_import_clears_stale_m772_runtime_counters(self):
        app = (ROOT / "ios" / "ARProbeApp.m").read_text()
        bridge = (ROOT / "runtime" / "m772_bridge.cpp").read_text()
        self.assertIn("ar_m772_runtime_begin();", app)
        begin = bridge.split('extern "C" void ar_m772_runtime_begin(void)', 1)[1]
        self.assertIn("m772_dispatch_count, UINT64_C(0)", begin)
        self.assertIn("m772_last_guest_pc, 0u", begin)
        self.assertIn("m772_initialized, 0u", begin)

    def test_process_tls_is_bounded_by_the_allocated_guest_vm(self):
        bridge = (ROOT / "ios" / "ARLivePPUBridge.c").read_text()
        runtime = (ROOT / "runtime" / "m772_bridge.cpp").read_text()
        self.assertIn("const uint32_t process_tls_image=stack_top", bridge)
        self.assertIn("stack_top>cap || tls_mem>cap-process_tls_image", bridge)
        self.assertIn("tls_image > ppu_vm_size || tls_memsz > ppu_vm_size - tls_image", runtime)
        self.assertIn("tls_image < stack_top", runtime)
        self.assertNotIn("0x10f00000u", runtime)


if __name__ == "__main__":
    unittest.main()
