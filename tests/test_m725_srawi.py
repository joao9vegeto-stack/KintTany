"""M7.25 independent synthetic Power ISA SRAWI cases for actual C AOT output.

Checks 32-bit signed result, PPC64 sign-extension, XER.CA and CR0.
No game code or commercial bytes.
"""
from __future__ import annotations
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_m23_cfg_lifter import run_c, BLR
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ppu_cfg_lifter import lift

def srawi(rs=3,ra=4,sh=1,rc=0):
    return (31<<26)|(rs<<21)|(ra<<16)|(sh<<11)|(824<<1)|rc

class SrawiM725(unittest.TestCase):
    def test_negative_odd_sets_carry_and_sign_extends(self):
        run_c([srawi(),BLR],regs={3:0xfffffffd},checks=[
            "rc==0","ctx.gpr[4]==0xfffffffffffffffeULL",
            "(ctx.xer&0x20000000U)!=0"])
    def test_negative_even_clears_carry(self):
        run_c([srawi(),BLR],regs={3:0xfffffffc},checks=[
            "rc==0","ctx.gpr[4]==0xfffffffffffffffeULL",
            "(ctx.xer&0x20000000U)==0"])
    def test_positive_word_no_sign_extension(self):
        run_c([srawi(sh=1),BLR],regs={3:0x7fffffff},checks=[
            "rc==0","ctx.gpr[4]==0x3fffffffULL",
            "(ctx.xer&0x20000000U)==0"])
    def test_shift_zero_and_alias_safely(self):
        run_c([srawi(rs=3,ra=3,sh=0),BLR],regs={3:0xffffffff},checks=[
            "rc==0","ctx.gpr[3]==0xffffffffffffffffULL",
            "(ctx.xer&0x20000000U)==0"])
    def test_shift_31_record_updates_cr0(self):
        source,hist=lift([srawi(sh=31,rc=1),BLR],0x10000)
        self.assertEqual(hist.get("srawi"),1)
        self.assertNotIn("ar_ppc_fallback_step",source)
        run_c([srawi(sh=31,rc=1),BLR],regs={3:0xffffffff},checks=[
            "rc==0","ctx.gpr[4]==0xffffffffffffffffULL",
            "(ctx.xer&0x20000000U)!=0",
            "(ctx.cr&0xf0000000U)==0x80000000U"])

if __name__=="__main__":unittest.main()
