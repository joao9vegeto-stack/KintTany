"""Original AArch64 producer sites, exact instruction emulation and functional reader ABI."""
import ast,re,unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]/"scripts/repack_ktgl_source_dual_repair.py"
class SignedProducer(unittest.TestCase):
 def setUp(self):
    self.source=SRC.read_text()
    t=ast.parse(self.source)
    self.host=ast.literal_eval(next(x.value for x in t.body
      if isinstance(x,ast.Assign) and len(x.targets)==1 and
         isinstance(x.targets[0],ast.Name) and x.targets[0].id=="HOST_C"))
 def test_original_return_and_clear_path_are_signed(self):
    self.assertIn("0xc107d8:bytes.fromhex(\"f40319aa\")",self.source)
    self.assertIn("0xc11f54:bytes.fromhex(\"880640f9\")",self.source)
    self.assertIn("Signed guest production/read opcode drift",self.source)
    self.assertIn("original_mode4_return_site",self.source)
    self.assertIn("original_direct_reader_source_reset_site",self.source)
 def test_producer_emulates_original_mov_without_touching_result(self):
    self.assertIn("FAIRY2_MODE4_PRODUCER_RETURN",self.host)
    self.assertIn("uc->uc_mcontext->__ss.__x[20]=uc->uc_mcontext->__ss.__x[25];",self.host)
    self.assertIn("uc->uc_mcontext->__ss.__pc=pc+4;",self.host)
    # A comparison x0==0 is NOT an assignment; reject only a true
    # assignment while allowing the legitimate original failure check.
    self.assertIsNone(re.search(r"uc->uc_mcontext->__ss\.__x\[0\]\s*=(?!=)",self.host))
 def test_direct_reader_real_fault_emulation(self):
    self.assertIn("FAIRY2_DIRECT_SOURCE_RESET",self.host)
    self.assertIn("vm_read_overwrite(mach_task_self()",self.host)
    self.assertIn("uc->uc_mcontext->__ss.__x[8]=source;",self.host)
    self.assertIn("if(kr!=KERN_SUCCESS||nread!=8)return 0;",self.host)
    self.assertIn("uc->uc_mcontext->__ss.__x[19]",self.host)
    self.assertIn("uc->uc_mcontext->__ss.__x[21]",self.host)
    self.assertIn("uc->uc_mcontext->__ss.__x[23]",self.host)
 def test_native_read_abi_remains_fixed(self):
    self.assertEqual(self.host.count("return consumed;"),2)
    self.assertNotIn("return r->cur;",self.host)
if __name__=="__main__":unittest.main()
