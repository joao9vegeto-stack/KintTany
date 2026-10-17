"""M7.34 PPC64 XS SRADI: 6-bit shift, XER.CA and native AOT semantics."""
import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_m23_cfg_lifter import run_c,BLR
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ppu_cfg_lifter import lift

def sradi(rs=27,ra=26,sh=63,rc=0):
 return ((31<<26)|(rs<<21)|(ra<<16)|((sh&31)<<11)|
         (413<<2)|((sh>>5)<<1)|rc)

class TestM734Sradi(unittest.TestCase):
 def test_exact_frontier_word_is_63_bit_sradi(self):
  self.assertEqual(sradi(),0x7f7afe76)
  c,h=lift([sradi(),BLR],0x52aa1c)
  self.assertEqual(h['sradi'],1)
  self.assertIn('ar_shift_src_0',c)
  self.assertIn('0x7fffffffffffffffULL',c)
  self.assertNotIn('ar_ppc_fallback_step',c)
 def test_positive_negative_and_negative_one_carry(self):
  run_c([sradi(),BLR],regs={27:11},
       checks=['rc==0','ctx.gpr[26]==0ULL','(ctx.xer&0x20000000U)==0'])
  run_c([sradi(),BLR],regs={27:0xfffffffffffffff5},
       checks=['rc==0','ctx.gpr[26]==UINT64_MAX',
               '(ctx.xer&0x20000000U)!=0'])
  run_c([sradi(),BLR],regs={27:0xffffffffffffffff},
       checks=['rc==0','ctx.gpr[26]==UINT64_MAX',
               '(ctx.xer&0x20000000U)!=0'])
 def test_64bit_min_has_no_carry_when_shift_63(self):
  run_c([sradi(),BLR],regs={27:0x8000000000000000},
       checks=['rc==0','ctx.gpr[26]==UINT64_MAX',
               '(ctx.xer&0x20000000U)==0'])
 def test_shift_zero_retains_input_and_zeroes_carry(self):
  run_c([sradi(sh=0),BLR],regs={27:0xfffffffffffffff5},
       checks=['rc==0','ctx.gpr[26]==0xfffffffffffffff5ULL',
               '(ctx.xer&0x20000000U)==0'])
 def test_record_updates_cr0_and_preserves_so(self):
  # 0 -> CR0 EQ, and zero shift; no undefined shifts.
  code,h=lift([sradi(rc=1),BLR],0x52aa1c)
  self.assertEqual(h['sradi'],1)
  self.assertIn('c->cr',code)
  run_c([sradi(rc=1),BLR],regs={27:0},
       checks=['rc==0','ctx.gpr[26]==0','((ctx.cr>>28)&0xfU)==2U'])
 def test_shift_13_uses_nine_bit_xs_opcode(self):
  code,h=lift([sradi(rs=0,ra=0,sh=13),BLR],0x52aa44)
  self.assertEqual(h['sradi'],1)
  self.assertIn('>> 13U',code)
if __name__=='__main__':unittest.main()
