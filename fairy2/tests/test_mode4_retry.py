"""Original-asset G1T/G1S bounded retry regressions, Linux-only."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
fake=types.ModuleType("repack_full_resource_va")
fake.patch_main=lambda *args:None
fake.verify_main=lambda *args:None
def require(v,why):
    if not v:raise ValueError(why)
fake.require=require
sys.modules["repack_full_resource_va"]=fake
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("repack_mode4_retry",ROOT/"scripts"/"repack_mode4_retry.py")
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class Mode4OriginalRetry(unittest.TestCase):
    def test_no_embedded_asset_rescue(self):
        src=r.bounded_retry_source()
        self.assertNotIn("fairy2_known_g1t",src)
        self.assertNotIn("fairy2_g1t_recovery_attempted",src)
        self.assertIn("FAIRY2_MODE4_ORIGINAL_STREAM_RETRY",src)
        self.assertNotIn("FAIRY2_G1T_RECOVERY",src)
    def test_exact_native_guest_entry_contract(self):
        src=r.bounded_retry_source()
        self.assertIn("s->off == 0x612120ULL",src)
        self.assertIn("s->off == 0x6e7bb0ULL",src)
        self.assertIn("x27 == (uint64_t)(uintptr_t)m->base + 0x2c15c40ULL",src)
        self.assertIn("=0x61210cULL;",src)
        self.assertIn("=0x6e7b94ULL;",src)
        self.assertIn("== 0 && fairy2_g1s_attempts < 64",src)
        self.assertIn("fairy2_g1t_attempts < 64",src)
        self.assertIn("if (!taken) fairy2_g1t_attempts=0",src)
        self.assertIn("if (!taken) {",src)
        self.assertIn("*(const uint64_t *)(uintptr_t)reader",src)
        self.assertIn("__x[26]",src)
    def test_18_original_branch_emulation(self):
        self.assertEqual(len(r.stage.TRACE_SITES),18)
        by_site={x[0]:x for x in r.stage.TRACE_SITES}
        self.assertEqual(by_site[0x6e7bb0][1],"81780054")
        self.assertEqual(by_site[0x612120][1],"a0050054")
        for at,op,target,kind,name in r.stage.TRACE_SITES:
            r.stage.verify_encoded_branch(at,bytes.fromhex(op),target,kind)
    def test_current_g1s_probe_and_fs_trace_remain(self):
        self.assertIn("FAIRY2_G1S_READER first_read",r.bounded_retry_source())
        self.assertTrue(callable(r.reader.patch_host_fs_trace))
    def test_workflow_selects_only_new_script(self):
        workflow=(ROOT.parent/".github"/"workflows"/"fairy2-g1s-readertrace.yml").read_text()
        self.assertIn("fairy2/mode4_retry_trigger.json",workflow)
        self.assertIn("repack_mode4_retry.py",workflow)
        self.assertIn("mode4-retry-report.json",workflow)
        self.assertIn("Fairy2iOS-FairyTail2-Mode4-BoundedRetry.ipa",workflow)
        self.assertNotIn("repack_g1s_readertrace.py \\",workflow)

if __name__=="__main__":unittest.main()
