"""Synthetic nm regression: undefined AOT refs never count as linked ARM64 code."""
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/"tools"))
from stage_m78_aot import EXPECTED_SYMBOLS, M712_NEXT_PC
from verify_m712_macho import verify
class M712MachO(unittest.TestCase):
 def test_exact_defined_macho_guest_code(self):
  names=sorted(set(EXPECTED_SYMBOLS)|{M712_NEXT_PC})
  nm="\n".join(f"000000000010{i:04x} T _{x}" for i,x in enumerate(names))
  self.assertEqual(verify(nm,"\n".join(names),len(names)),60)
  with self.assertRaisesRegex(ValueError,"code symbol mismatch"):
   verify(nm.replace(" T _ar_game_ppu_002c1664"," U _ar_game_ppu_002c1664"),"\n".join(names),len(names))
  with self.assertRaisesRegex(ValueError,"wrong number"):
   verify(nm,"\n".join(names),len(names)+1)
if __name__=="__main__":unittest.main()
