"""M6.4 real GOWA.ELF opcode 0x79040020: PowerPC MD semantics."""
import unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]
C=(P/"ios/ARPrivateELFProbe.c").read_text()
U=(P/"ios/ARProbeApp.m").read_text()
W=(P/".github/workflows/ascension-recomp-m0.yml").read_text()
H=(P/"tests/host_m64_ppu.c").read_text()
class PPU32(unittest.TestCase):
 def test_rotation_decode_and_bit_mask(self):
  for t in ("int ar_ppu_rldicl(", "((w>>2)&7u)!=0u",
            "const unsigned sh=","const unsigned mb=",
            "UINT64_MAX>>(mb)", "ar_ppu_rldicl(w,gpr[rt],&rotated)",
            "gpr[ra]=rotated;","0x79040020","return -998"):
   self.assertIn(t,C)
  for t in ("0x79040020u","UINT64_C(0x12345678fedcba98)",
      "UINT64_C(0xfedcba98)","0x79040021u","0x79040024u",
      "cpu[9]!=0xffffffffu"):
   self.assertIn(t,H)
 def test_no_regression_sandbox(self):
  for t in ("for(unsigned step=0;step<16;step++)",
      "for(unsigned step=0;step<24;step++)",
      "for(unsigned step=0;step<32;step++)",
      "if(step==15u &&","uint8_t stack[4096]",
      "out[7]=w;out[8]=pc;","out[9]=(uint32_t)gpr[4]",
      "return -990;"):
   self.assertIn(t,C)
 def test_32_step_order_and_organized_tabs(self):
  i=U.index("ar_ppu_bootstrap_twentyfour(data.bytes,data.length,info,cpu24)")
  j=U.index("ar_ppu_bootstrap_thirtytwo(data.bytes,data.length,info,cpu32)")
  self.assertLess(i,j)
  for t in ("M6.4 PARADA SEGURA","M6.4 PPU REAL 32/32: OK",
      "self.gameList.hidden=!showGame",
      "self.graphicsList.hidden=showGame",
      "ASCENSIONRECOMP   ·   M7.59"):
   self.assertIn(t,U)
 def test_ci(self):
  for t in ("host_m64_ppu.c","m64-host.log","m64-status.txt",
    "M6.4 PPU32 and rldicl PASS","0.6.22-unsigned.ipa"):
   self.assertIn(t,W)
if __name__=="__main__":unittest.main()
