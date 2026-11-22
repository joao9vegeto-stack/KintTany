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
if __name__=="__main__":unittest.main()
