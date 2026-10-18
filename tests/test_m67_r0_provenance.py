"""M6.7 register provenance: no bypass for a false bctrl code pointer."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
U=(R/"ios/ARProbeApp.m").read_text()
H=(R/"tests/host_m67_trace.c").read_text()
W=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
class Provenance(unittest.TestCase):
 def test_legacy_fortyeight_abi_unchanged(self):
  self.assertIn("int ar_ppu_bootstrap_fortyeight_trace(",C)
  self.assertIn("int ar_ppu_bootstrap_fortyeight(",C)
  self.assertIn("return ar_ppu_bootstrap_fortyeight_trace(d,len,info,out,NULL);",C)
  self.assertIn("if(dest>UINT32_MAX || !lookup(d,len,ss,used,dest,4,1))",C)
  self.assertIn("return -1007;",C)
 def test_track_only_guest_values(self):
  for token in ("if(trace)memset(trace,0,24*sizeof(*trace))",
      "const uint64_t prior_r0=gpr[0];",
      "trace[16u+2u*ix]=pc;","trace[17u+2u*ix]=w;",
      "if(trace && gpr[0]!=prior_r0)",
      "trace[0]=pc;trace[1]=w;",
      "trace[3]=(uint32_t)gpr[0];",
      "trace[7]++;","trace[10]=pc;trace[11]=rt;",
      "trace[14]=pc;","trace[15]++;"):
   self.assertIn(token,C)
 def test_report_is_only_user_action(self):
  for token in ("self.ppuReportButton=reportButton;",
      "Copiar diagnóstico PPU",
      "UIPasteboard.generalPasteboard.string=self.ppuReport;",
      "self.ppuReportButton.enabled=YES;",
      "ar_ppu_bootstrap_fortyeight_trace(",
      "trace48[0],trace48[1]",
      "ASCENSIONRECOMP   ·   M7.52"):
   self.assertIn(token,U)
 def test_host_and_ci(self):
  for token in ("trace[0]!=0x10080u","trace[1]!=0x6000006cu",
                "trace[14]!=0x100a8u","trace[3]!=0x100e4u",
                "M6.7 bounded r0 provenance CTR trace PASS"):
   self.assertIn(token,H)
  for token in ("m67-host.log","m67-status.txt",
          "tests/host_m67_trace.c","0.6.22-unsigned.ipa"):
   self.assertIn(token,W)
if __name__=="__main__":unittest.main()
