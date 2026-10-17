"""M7.30 Power ISA MFCR native PPC->C lifter, strict full-CR XFX form."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_m23_cfg_lifter import run_c,BLR
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ppu_cfg_lifter import lift,Unsupported
def mfcr(rd=12):return 0x7c000026|(rd<<21)
class M730MFCR(unittest.TestCase):
 def test_real_frontier_encoding_mfcr_r12(self):
  src,h=lift([0x7d800026,BLR],0x10000)
  self.assertEqual(h["mfcr"],1)
  self.assertIn("c->gpr[12]=(u64)c->cr;",src)
  self.assertNotIn("ar_ppc_fallback_step",src)
 def test_native_mfcr_gpr32_zero_extended(self):
  run_c([0x7d800026,BLR],checks=["rc==0","ctx.gpr[12]==0ULL","ctx.cia==0x1234ULL"])
  run_c([0x7d800026,BLR],regs={12:0xffffffffffffffff},
        checks=["rc==0","ctx.gpr[12]==0ULL","ctx.cr==0U"])
 def test_mfcr_multiple_destinations_and_no_side_effects(self):
  run_c([mfcr(1),mfcr(31),mfcr(0),BLR],regs={1:7,31:9,0:3},
        checks=["rc==0","ctx.gpr[1]==0ULL","ctx.gpr[31]==0ULL",
                "ctx.gpr[0]==0ULL","ctx.xer==0U"])
 def test_mfocrf_and_reserved_forms_fail_closed(self):
  for w in (0x7d900026,0x7d810026,0x7d800027,0x7d880026):
   with self.subTest(opcode=f"{w:08x}"):
    with self.assertRaises(Unsupported):lift([w,BLR],0x10000)
 def test_native_executable_lifter_still_no_interpreter(self):
  src,h=lift([mfcr(12),BLR],0x10000,"test_m730_owner_frontier_synthetic")
  self.assertEqual(h.get("mfcr"),1)
  self.assertNotIn("ar_guest_call",src)
if __name__=="__main__":unittest.main()
