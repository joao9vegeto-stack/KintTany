"""The diagnostic preserves original G1T branch flags and host fs semantics."""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/"scripts"))
import repack_ktgl_transaction_trace as trace

FS_TEMPLATE="""#include "save_sync.h"\nint some_neighbor(void) { return 1; }
void h_fs_ReadFile_implementation(void) {
    size_t got = 0; int reprep = 0, fd = (int)h; int64_t base = 0;
    *out = got;
    if (g_fslog) { return; }
}
"""
CRASH_TEMPLATE="""static void on_crash(int sig, siginfo_t *si, void *uc_) {
    ucontext_t *uc = uc_;
    if (sig == SIGTRAP && g_trap_hook && g_trap_hook(uc)) return;
}
"""

class RealTransactionTest(unittest.TestCase):
    def test_pinned_original_bin_and_exact_b_eq(self):
        self.assertEqual(trace.SOURCE_G1T,0x612120)
        self.assertEqual(trace.SOURCE_ADAPTER,0xc09728)
        self.assertEqual(trace.SOURCE_ADAPTER_OPCODE.hex(),"000840f9")
        self.assertEqual(trace.SOURCE_BOUND_POST,0xc0962c)
        self.assertEqual(trace.SOURCE_BOUND_OPCODE.hex(),"880200cb")
        self.assertEqual(trace.FDATA_PACKET_END,0x2fe179)
        self.assertEqual(trace.FDATA_PACKET_END,0x280000+0x7e179)
        self.assertEqual(trace.SOURCE_OPCODE.hex(),"a0050054")
        self.assertEqual(trace.BREAK.hex(),"40403ed4")
        self.assertEqual(trace.G1T_FDATA_IMG_ENTRY,12943)
        self.assertEqual(trace.G1T_FDATA_RECORD_OFFSET,3137776)
        self.assertEqual(trace.G1T_FDATA_DATA_OFFSET,3137864)
        self.assertEqual(trace.G1T_FDATA_COMPRESSED_BYTES,49)

    def test_injection_is_observation_only_and_limits_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            host=root/"engine/dm/host"
            host.mkdir(parents=True)
            (host/"hle_fs.c").write_text(FS_TEMPLATE)
            (host/"crash.c").write_text(CRASH_TEMPLATE)
            trace.patch_host(root)
            fs=(host/"hle_fs.c").read_text()
            crash=(host/"crash.c").read_text()
            self.assertEqual(fs.count("FAIRY2_FDATA_TRANSACTION:"),1)
            self.assertIn("FAIRY2_G1T_SOURCE_PACKET",fs)
            self.assertIn("filehash==0xfb9ebd24u && typehash==0xafbec60cu",fs)
            self.assertIn("3137913ull",fs)
            self.assertIn("FAIRY2_G1T_SOURCE_PACKET original IDRK+zlib",fs)
            self.assertIn("f2_adapter_original_load(uc)",crash)
            self.assertIn("f2_wrapper_post_read(uc)",crash)
            self.assertLess(crash.index("f2_wrapper_post_read(uc)"),
                            crash.index("f2_adapter_original_load(uc)"))
            self.assertIn("f2_trace_original_packet_and_reader();",crash)
            self.assertIn("IMG_K(h)",fs)
            self.assertIn("f2_key==12943 || f2_key==13660",fs)
            self.assertIn("f2_seq<=256",fs)
            self.assertIn("*out = got;",fs)
            self.assertIn("if (g_fslog) { return; }",fs)  # original log path preserved
            self.assertEqual(fs.count("size_t got = 0; int reprep = 0"),1)
            self.assertIn("f2_g1t_validator_branch(uc)",crash)
            self.assertIn("g_trap_hook && g_trap_hook(uc)",crash)
            self.assertLess(crash.index("f2_g1t_validator_branch(uc)"),
                            crash.index("g_trap_hook && g_trap_hook(uc)"))
            with self.assertRaises(AssertionError):
                trace.patch_host(root)  # fail-closed double patch

    def test_real_native_trace_does_not_forge_a_byte(self):
        source=(HERE/"scripts/ktgl_transaction_trace_host.h").read_text()
        self.assertIn("PSTATE.Z",source)
        self.assertIn("0x6121d4u:0x612124u",source)
        self.assertIn("vm_read_overwrite",source)
        self.assertIn("FAIRY2_G1T_VALIDATOR_REAL_FAIL",source)
        self.assertIn("FAIRY2_STREAM_ADAPTER",source)
        self.assertIn("FAIRY2_READ_PROVENANCE",source)
        self.assertIn("f2_adapter_x3_local=uc->uc_mcontext->__ss.__x[3]",source)
        self.assertIn("uc->uc_mcontext->__ss.__x[8]=quota-got",source)
        self.assertIn("m->base+0xc09630u",source)
        self.assertIn("FAIRY2_G1T_CACHE_PROOF",source)
        self.assertIn("f2_adapter_peek(adapter+0x10,&backing,sizeof backing)",source)
        self.assertIn("m->base+0xc0972cu",source)
        self.assertIn("original_137B_same",source)
        self.assertNotIn("memcpy(dest",source)
        self.assertNotIn("retry",source.split("static int f2_g1t_validator_branch",1)[1])
        script=(HERE/"scripts/repack_ktgl_transaction_trace.py").read_text()
        self.assertIn("not_for_auto_transfer",script)
        self.assertIn("file_read_behavior_unchanged",script)
        self.assertIn("original_G1T_branch_result_unchanged",script)
        self.assertIn("guest_read_return_forged",script)
        self.assertIn("source_packet_137_byte_guest_integrity_probed",script)
        self.assertIn("original_adapter_load_emulated",script)
        self.assertIn("original_bounded_sub_emulated",script)
        self.assertIn("last_64_original_reads_on_failure",script)
        self.assertNotIn("FAIRY2_MODE4_ORIGINAL_ZLIB_RECOVERED",script)

if __name__=="__main__":unittest.main()
