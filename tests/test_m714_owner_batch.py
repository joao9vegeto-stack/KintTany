"""M7.14 owner-only multi-entry PPC AOT planner. Synthetic code only."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from m714_owner_batch import plan, terminal_word

class SyntheticExecutable:
    def __init__(self):
        self.words_at={0x1000:0x38630001,0x1004:0x4e800020,
                       0x2000:0x38630001,0x2004:0x60000000,
                       0x2008:0x60000000}
    def words(self,start,end):
        from ppu_cfg_lifter import Unsupported
        if end-start!=4 or start not in self.words_at:
            raise Unsupported('no executable code at this address')
        return (self.words_at[start],)

class M714OwnerBatchTests(unittest.TestCase):
    def test_terminal(self):
        self.assertTrue(terminal_word(0x4e800020))
        self.assertFalse(terminal_word(0x38630001))
        self.assertFalse(terminal_word(0x48000005))
    def test_batched_candidate_and_safe_rejection(self):
        r=plan(SyntheticExecutable(),[0x2000,0x1000],8)
        self.assertEqual(r['requested'],2)
        self.assertEqual(len(r['accepted']),1)
        self.assertEqual(r['accepted'][0]['end'],'0x00001008')
        self.assertEqual(len(r['rejected']),1)
    def test_reject_duplicated_and_unbounded(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            plan(SyntheticExecutable(),[0x1000,0x1000])
        with self.assertRaisesRegex(ValueError,'unbounded'):
            plan(SyntheticExecutable(),[0x1000],513)

if __name__=='__main__':unittest.main()
