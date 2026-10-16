"""M6.3: never claim 24 guest steps if instruction/stack fail."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
U=(R/"ios/ARProbeApp.m").read_text()
W=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
class TwentyFour(unittest.TestCase):
 def test_original_sixteen_kept(self):
  self.assertIn("for(unsigned step=0;step<16;step++)",C)
  self.assertIn("ar_ppu_bootstrap_sixteen(data.bytes,data.length,info,cpu16)",U)
 def test_bounded_next_steps(self):
  for x in ("int ar_ppu_bootstrap_twentyfour(",
            "for(unsigned step=0;step<24;step++)",
            "if(step==15u &&",
            "out[7]=w;out[8]=pc;",
            "uint8_t stack[4096]",
            "if(va<base||va>base+sizeof(stack)-4)return -995;",
            "if(gpr[2]!=info[2])return -997;",
            "lookup(d,len,ss,used,pc,4,1)"):
   self.assertIn(x,C)
 def test_ppu_and_ui(self):
  for x in ("ar_ppu_bootstrap_twentyfour(data.bytes,data.length,info,cpu24)",
            "M6.2 PPU REAL 16/16: OK",
            "M6.3 PARADA SEGURA",
            "M6.3 PPU REAL 24/24: OK",
            "cpu24[8],cpu24[7]",
            "self.gameList.hidden=!showGame",
            "self.graphicsList.hidden=showGame"):
   self.assertIn(x,U)
 def test_ci(self):
  for x in ("m63-host.log","m63-status.txt",
            "host_m63_ppu.c","0.6.9-unsigned.ipa"):
   self.assertIn(x,W)
if __name__=="__main__":unittest.main()
