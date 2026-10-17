"""M7.22: compile and execute true C/ARM64-liftable PPC blocks using ONLY
synthetic words. Host C compile/run distinguishes AOT from interpretation.
Commercial owner GOWA.ELF and generated sources never enter public CI.
"""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_m23_cfg_lifter import run_c, BLR
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ppu_cfg_lifter import lift

def mform(op,rs,ra,sh,mb,me,rc=0):
    return (op<<26)|(rs<<21)|(ra<<16)|(sh<<11)|(mb<<6)|(me<<1)|rc

def xoform(xo,rt,ra,rb,rc=0):
    return (31<<26)|(rt<<21)|(ra<<16)|(rb<<11)|(xo<<1)|rc

class NativeAOTM722(unittest.TestCase):
    def test_rlwimi_masks_and_preserves_destination(self):
        instructions=[mform(20,3,4,24,1,5),BLR]
        src,counts=lift(instructions,0x10000)
        self.assertEqual(counts["rlwimi"],1)
        self.assertIn("ar_data32(",src)
        self.assertNotIn("ar_ppc_fallback_step",src)
        run_c(instructions,regs={3:0xab,4:0xfeedface12345678},
              checks=['rc==0','ctx.gpr[4]==0xfeedface2a345678ULL'])
    def test_wrapped_rlwimi_ppc64_mask_upper_half(self):
        run_c([mform(20,3,4,0,28,3),BLR],
              regs={3:0x12345678,4:0xabcdef0100000000},
              checks=['rc==0','ctx.gpr[4]==0x1234567810000008ULL'])
    def test_rlwnm_register_shift_and_rlwinm_mask(self):
        run_c([mform(23,3,4,5,0,31),BLR],
              regs={3:0x12345678,5:40},
              checks=['rc==0','ctx.gpr[4]==0x34567812ULL'])
        run_c([mform(21,3,4,0,28,3),BLR],
              regs={3:0x12345678},
              checks=['rc==0','ctx.gpr[4]==0x1234567810000008ULL'])
    def test_rlwimi_record_updates_cr0_and_preserves_other_fields(self):
        run_c([mform(20,3,4,0,1,5,1),BLR],
              regs={3:0,4:0},
              checks=['rc==0','(ctx.cr & 0xf0000000U)==0x20000000U'])
    def test_divwu_mullw_subfc_exact_32_64_semantics(self):
        for xo,a,b,expected in [
            (459,20,4,5),
            (235,0xffffffff,2,0xfffffffffffffffe),
            (8,1,0,0xffffffffffffffff)]:
            ins=[xoform(xo,3,4,5),BLR]
            run_c(ins,regs={4:a,5:b},
                  checks=['rc==0',f'ctx.gpr[3]==0x{expected:x}ULL'])
    def test_divide_zero_fails_closed_no_partial_state(self):
        run_c([xoform(459,3,4,5),BLR],regs={3:99,4:10,5:0},
              checks=['rc==-12','ctx.gpr[3]==99ULL'])
    def test_all_unsupported_opcodes_still_rejected(self):
        from ppu_cfg_lifter import Unsupported
        with self.assertRaises(Unsupported):
            lift([0xffffffff,BLR],0x10000)

if __name__=="__main__":
    unittest.main()
