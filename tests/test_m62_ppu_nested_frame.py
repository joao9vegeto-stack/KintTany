"""M6.2: bounded CPU16, fail-closed mflr and stack."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
C=(ROOT/"ios/ARPrivateELFProbe.c").read_text()
UI=(ROOT/"ios/ARProbeApp.m").read_text()
WORK=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
class Frame(unittest.TestCase):
 def test_strict_decoder(self):
  for token in ("for(unsigned step=0;step<16;step++)",
                "uint8_t stack[4096]",
                "((w>>1)&1023u)==339u",
                "((w>>11)&1023u)==256u",
                "return -967","return -969","return -970",
                "stores!=9u||mflr!=1u"):
   self.assertIn(token,C)
 def test_gates(self):
  self.assertIn("ar_ppu_bootstrap_sixteen(data.bytes,data.length,info,cpu16)",UI)
  self.assertIn("M6.2 PPU REAL 16/16: OK",UI)
  self.assertIn("M6.1 PPU REAL 8/8: OK",UI)
  self.assertIn("testM58AlphaTest:",UI)
  self.assertIn("m62-host.log",WORK)
  self.assertIn("0.6.10-unsigned.ipa",WORK)
if __name__=="__main__":unittest.main()
