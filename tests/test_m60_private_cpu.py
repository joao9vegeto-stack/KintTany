"""M6.0 fail-closed four-step PPU device gate."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
A=(R/"ios/ARProbeApp.m").read_text()
W=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
class PPU4(unittest.TestCase):
 def test_guest_instruction_barriers(self):
  for s in ("for(unsigned step=0;step<4;step++)",
            "if(op==14)","else if(op==25)","else if(op==24)",
            "else if(op==32)","return -936","return -935","return -937"):
   self.assertIn(s,C)
 def test_device_integration_and_older_paths(self):
  self.assertIn("ar_ppu_bootstrap_four(data.bytes,data.length,info,cpu)",A)
  self.assertIn("M5.9 NPUA80918: ELF REAL VALIDADO",A)
  self.assertIn("testM58AlphaTest:",A)
  self.assertIn("m60-host.log",W)
  self.assertIn("0.6.21-unsigned.ipa",W)
  self.assertNotIn("GOWA.SELF",C)
if __name__=="__main__":unittest.main()
