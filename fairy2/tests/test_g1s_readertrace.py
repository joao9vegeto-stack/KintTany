import sys,types,unittest,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
base=types.ModuleType("repack_full_resource_va")
base.patch_main=lambda *args:None
base.verify_main=lambda *args:None
def require(v,msg):
    if not v:raise ValueError(msg)
base.require=require
sys.modules["repack_full_resource_va"]=base
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("g1s_readertrace",ROOT/"scripts/repack_g1s_readertrace.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class G1SReaderTests(unittest.TestCase):
    def test_exact_native_branches(self):
        self.assertEqual(len(mod.stage.TRACE_SITES),18)
        for at,op,target,kind,name in mod.NEW_SITES:
            mod.stage.verify_encoded_branch(at,bytes.fromhex(op),target,kind)
    def test_bad_opcode_fails_closed(self):
        at,op,dest,kind,label=mod.NEW_SITES[0]
        with self.assertRaises(ValueError):
            mod.stage.verify_encoded_branch(at,bytes.fromhex(op),dest+4,kind)
    def test_dump_proves_first_native_184_bytes(self):
        host=mod.host_trace_source()
        self.assertIn("FAIRY2_G1S_READER first_read=",host)
        self.assertIn("guest_reader=",host)
        self.assertIn("first24=",host)
        self.assertIn("0x6e7bb0ULL",host)
        self.assertNotIn("mprotect(",host)
    def test_native_G1S_factory(self):
        sites={x[0]:x for x in mod.NEW_SITES}
        self.assertEqual(sites[0x1dbdcac][2],0x1dbdd04)
        self.assertEqual(sites[0x6e7bb0][2],0x6e8ac0)
    def test_host_fs_probe_is_bound_to_original_image_handles(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)/"hle_fs.c"
            fake.write_text(
                'HLE_FORCE("_ZN2nn2fs8ReadFileEPmNS0_10FileHandleElPvm", "fsp-srv → pread(2)", Result, h_fs_ReadFile, size_t *out, uint64_t h, int64_t off, void *buf, size_t sz) { dm_thread_service_request();\n'
                '    size_t got = 0; int reprep = 0, fd = (int)h; int64_t base = 0;\n'
                '            return err_res("pread", "fd"); }\n'
                '    *out = got;\n'
                '}\n'
                'HLE_FORCE("_ZN2nn2fs9WriteFileENS0_10FileHandleElPKvmRKNS0_11WriteOptionE" )\n'
            )
            mod.patch_host_fs_trace(fake)
            changed = fake.read_text()
            self.assertIn("FAIRY2_FDATA_IO_PROOF", changed)
            self.assertIn("FAIRY2_FDATA_IO_ZERO", changed)
            self.assertIn("FAIRY2_FDATA_IO_HISTORY", changed)
            self.assertIn("IMG_K(h) == 12943 || IMG_K(h) == 13660", changed)
            self.assertIn("size_t requested = sz", changed)
            self.assertIn("*out = got", changed)
            self.assertIn('return err_res("pread", "fd")', changed)
            with self.assertRaises(ValueError):
                mod.patch_host_fs_trace(fake)
    def test_host_crash_prints_fs_after_trapped_guest_parser(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"crash.c"
            path.write_text("    if (sig == SIGTRAP) fairy2_stage_dump();\n"
                            "static void on_crash(int sig, siginfo_t *si, void *uc_) {}")
            mod.patch_host_crash_io(path)
            self.assertIn("fairy2_fdata_probe_dump();", path.read_text())
            self.assertIn("extern void fairy2_fdata_probe_dump(void);", path.read_text())
if __name__=="__main__":unittest.main()
