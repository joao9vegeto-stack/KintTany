from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
U=(R/"ios/ARProbeApp.m").read_text()
W=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
class PPU8(unittest.TestCase):
 def test_guards(self):
  for x in ("for(unsigned step=0;step<8;step++)",
            "uint8_t stack[4096]","return -947","return -949",
            "return -950","gpr[ra]=va","lr=next"):
   self.assertIn(x,C)
  self.assertIn("ar_ppu_bootstrap_eight(data.bytes,data.length,info,eight)",U)
  self.assertIn("M6.1 PPU REAL 8/8: OK",U)
  self.assertIn("m61-host.log",W)
  self.assertIn("0.6.10-unsigned.ipa",W)
if __name__=="__main__":unittest.main()
