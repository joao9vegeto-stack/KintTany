"""M7.26 Power ISA DIVDU 64-bit -> native AOT, synthetic words only."""
from __future__ import annotations
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_m23_cfg_lifter import run_c, BLR
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ppu_cfg_lifter import lift

def divdu(rt=3,ra=4,rb=5,rc=0):
    return (31<<26)|(rt<<21)|(ra<<16)|(rb<<11)|(457<<1)|rc

class DivduM726(unittest.TestCase):
    def test_unsigned_64bit_full_width_not_low_word(self):
        run_c([divdu(),BLR],regs={4:0x8000000000000000,5:2},
              checks=["rc==0","ctx.gpr[3]==0x4000000000000000ULL"])
    def test_result_and_divisor_alias_safe(self):
        run_c([divdu(rt=5),BLR],regs={4:0xffffffffffffffff,5:3},
              checks=["rc==0","ctx.gpr[5]==0x5555555555555555ULL"])
    def test_division_by_zero_fails_closed(self):
        run_c([divdu(),BLR],regs={3:77,4:10,5:0},
              checks=["rc==-12","ctx.gpr[3]==77ULL"])
    def test_record_and_trace_is_native_not_interpreted(self):
        src,hist=lift([divdu(rc=1),BLR],0x10000)
        self.assertEqual(hist.get("divdu"),1)
        self.assertNotIn("ar_ppc_fallback_step",src)
        run_c([divdu(rc=1),BLR],regs={4:1,5:3},
              checks=["rc==0","ctx.gpr[3]==0ULL",
                      "(ctx.cr & 0xf0000000U)==0x20000000U"])

if __name__=="__main__":unittest.main()
