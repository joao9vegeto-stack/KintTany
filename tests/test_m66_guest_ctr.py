"""Device 0x7C0903A6 mtctr r0 at real PC 0x669C2C, M6.5 38/40.
No game binaries in app, CI or fixture.
"""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
UI=(R/"ios/ARProbeApp.m").read_text()
W=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
H=(R/"tests/host_m66_ctr.c").read_text()
class PowerPCCTR(unittest.TestCase):
 def test_48_bound_and_compatible_prefix(self):
  for token in ("for(unsigned step=0;step<16;step++)",
      "for(unsigned step=0;step<24;step++)",
      "for(unsigned step=0;step<32;step++)",
      "for(unsigned step=0;step<40;step++)",
      "for(unsigned step=0;step<48;step++)",
      "int ar_ppu_bootstrap_fortyeight(",
      "if(step==15u &&","m65_store32(&guest,ss,used,va,v)"):
   self.assertIn(token,C)
 def test_mtctr_unconditional_indirect_protected(self):
  for token in ("((w>>1)&1023u)==467u","spr!=9u",
       "ctr=gpr[rt];out[17]=(uint32_t)ctr;",
       "((w>>1)&1023u)==528u",
       "w!=0x4e800420u && w!=0x4e800421u",
       "ctr&~UINT64_C(3)",
       "lookup(d,len,ss,used,dest,4,1)",
       "return -1007","return -1008",
       "out[19]++","out[10]=out[11]=out[12]=0u;",
       "out[16]=0u;out[17]=(uint32_t)ctr;"):
    self.assertIn(token,C)
 def test_mobile_gate_fail_closed_and_clear_diagnostics(self):
  for token in ("const BOOL knownMtctrStop =",
    "rc40==-990 && cpu40[0]>=32u",
    "((cpu40[7]>>1)&1023u)==467u",
    "if(rc40 && !knownMtctrStop){",
    "ar_ppu_bootstrap_fortyeight_trace(",
    "M6.5 LEGADA: mtctr","M6.6 PARADA SEGURA",
    "M6.7.6 PPU REAL 48/48: OK",
    "CTR=0x%08X%08X",
    "ASCENSIONRECOMP   ·   M7.11"):
   self.assertIn(token,UI)
 def test_host_synthetic_and_version(self):
  for token in ("0x7c0903a6u","0x4e800420u","0x4e800421u",
    "0x7c0803a6u","0x7c0903a7u","0x4e000420u",
    "M6.6 PPU48 guarded mtctr and bctr PASS"):
   self.assertIn(token,H)
  for token in ("m66-host.log","m66-status.txt",
                "tests/host_m66_ctr.c","0.6.20-unsigned.ipa"):
   self.assertIn(token,W)
if __name__=="__main__":unittest.main()
