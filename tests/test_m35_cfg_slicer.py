"""Synthetic-only PPU CFG reachability tests; never game bytes."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ppu_cfg_slicer import inspect,CFGRejected
BLR=0x4e800020; NOP=0x60000000
def cmpwi(reg,v):return (11<<26)|(reg<<16)|(v&0xffff)
def bc(bo,bi,delta):return (16<<26)|(bo<<21)|(bi<<16)|(delta&0xfffc)
def b(delta):return (18<<26)|(delta&0x3fffffc)
def li(rd,v):return (14<<26)|(rd<<21)|(v&0xffff)
class M35CFG(unittest.TestCase):
    def test_forward_jump_past_early_blr(self):
        r=inspect([cmpwi(3,5),bc(12,2,12),BLR,NOP,li(3,1),BLR],0x10000)
        self.assertEqual(r['guest_return_branches'],2)
        self.assertEqual(r['reachable_words'],5)
        self.assertEqual(r['unreachable_words'],1)
    def test_truncation_rejected(self):
        with self.assertRaisesRegex(CFGRejected,'crosses bound'):
            inspect([cmpwi(3,5),bc(12,2,12),BLR],0x10000)
    def test_ctr_loop(self):
        r=inspect([li(3,1),bc(16,0,-4),BLR],0x10000)
        self.assertEqual(r['reachable_words'],3)
    def test_unbounded_loop_rejected(self):
        with self.assertRaisesRegex(CFGRejected,'no guest return'):
            inspect([b(0)],0x10000)
    def test_tail_branch_requires_proof(self):
        with self.assertRaisesRegex(CFGRejected,'unverified tail'):
            inspect([b(0x20)],0x10000)
    def test_unbounded_fallthrough_rejected(self):
        with self.assertRaisesRegex(CFGRejected,'fallthrough'):
            inspect([NOP],0x10000)
    def test_conditional_bclr_two_paths(self):
        beqlr=(19<<26)|(12<<21)|(2<<16)|(16<<1)
        r=inspect([cmpwi(3,5),beqlr,li(3,2),BLR],0x10000)
        self.assertEqual(r['guest_return_branches'],2)
if __name__=='__main__':unittest.main()
