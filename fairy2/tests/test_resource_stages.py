"""Device trace must emulate exactly the overwritten guest instructions."""
from __future__ import annotations
import sys
import types
import unittest
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
FAKE = types.ModuleType('repack_full_resource_va')
FAKE.patch_main=lambda *args: None
FAKE.verify_main=lambda *args: None
def require(ok, message):
    if not ok: raise RuntimeError(message)
FAKE.require=require
sys.modules.setdefault('repack_full_resource_va',FAKE)
spec=importlib.util.spec_from_file_location('fairy2_stage_test',ROOT/'scripts/repack_resource_stages.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class G1TTraceTest(unittest.TestCase):
    def test_exact_arm64_branch_targets(self):
        for at, op, dest, kind, stage in mod.TRACE_SITES:
            with self.subTest(stage=stage):
                mod.verify_encoded_branch(at, bytes.fromhex(op), dest, kind)
    def test_bad_dest_rejected(self):
        at, op, dest, kind, _=mod.TRACE_SITES[0]
        with self.assertRaises(RuntimeError):
            mod.verify_encoded_branch(at, bytes.fromhex(op), dest + 4, kind)
    def test_missing_opcode_rejected_closed(self):
        buf=bytearray(max(x[0] for x in mod.TRACE_SITES)+4096)
        for at,op,*_ in mod.TRACE_SITES:buf[at:at+4]=bytes.fromhex(op)
        out=mod.trace_guest(bytes(buf))
        for at,op,*_ in mod.TRACE_SITES:
            self.assertEqual(out[at:at+4],mod.BRK)
            self.assertEqual(buf[at:at+4],bytes.fromhex(op))
        buf[mod.TRACE_SITES[0][0]]^=1
        with self.assertRaises(RuntimeError):mod.trace_guest(bytes(buf))
    def test_host_handler_syntax_and_isolation(self):
        src=mod.host_trace_source()
        self.assertEqual(src.count('0xD43E4040U'),1)
        self.assertEqual(src.count('case 0:'),1)
        self.assertEqual(src.count('case 4:'),1)
        for at,*_ in mod.TRACE_SITES:
            self.assertIn(f'{at:#x}ULL',src)
        self.assertNotIn('mprotect(',src)
        self.assertNotIn('mach_vm_',src)
    def test_one_shot_original_g1t_recovery(self):
        src=mod.host_trace_source()
        self.assertIn('FAIRY2_G1T_RECOVERY retry',src)
        self.assertIn('0x612120ULL && taken',src)
        self.assertIn('0x2c15c40ULL',src)
        self.assertIn('uc->uc_mcontext->__ss.__x[2] = uc->uc_mcontext->__ss.__x[26]',src)
        self.assertIn('uc->uc_mcontext->__ss.__x[23]',src)
        self.assertIn('fairy2_known_g1t_read',src)
        self.assertIn('fairy2_known_g1t_skip',src)
        self.assertIn('0x61210cULL',src)
        self.assertIn('FAIRY2_G1T_REJECT original header28',src)

    def test_no_in_place_rewrite_of_uncaught_resource(self):
        src=mod.host_trace_source()
        self.assertIn('taken ? s->target : s->off + 4',src)
        self.assertIn('fairy2_stage_dump',src)
        self.assertNotIn('skip resource',src)

if __name__=='__main__':unittest.main()
