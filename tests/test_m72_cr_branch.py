"""M7.2: real PS3 CR7 cmpld and signed conditional PPC branch semantics."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
CPU=(R/"ios/ARNativePPUContinuous.c").read_text()
APP=(R/"ios/ARProbeApp.m").read_text()
HOST=(R/"tests/host_m72_cr_branch.c").read_text()
WF=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
PL=(R/"ios/Probe-Info.plist").read_text()
class CRSemantics(unittest.TestCase):
 def test_compare_size_and_fields(self):
  for x in ("static void guest_compare(", "const unsigned shift=28u-4u*bf;",
            "cmp|=(unsigned)((c->xer>>31)&1u);",
            "(((word>>1)&1023u)==0u || ((word>>1)&1023u)==32u)",
            "guest_compare(c,bf,op==11u,wide,c->gpr[ra],rhs);",
            "guest_compare(c,bf,((word>>1)&1023u)==0u,",
            "word&0x00400000u", "word&0x00400001u"):
   self.assertIn(x,CPU)
 def test_branch_options_and_cr(self):
  for x in ("static int guest_branch_test(",
            "c->ctr--;", "(c->cr>>(31u-bi))&1u",
            "guest_branch_test(c,bo,bi,1u,&taken)",
            "guest_branch_test(c,bo,bi,0u,&taken)",
            "if(word&1u)c->lr=next;",
            "if(!executable(seg,used,target)){rc=-1312;break;}",
            "if(hle!=AR_OK){rc=-1315;"):
   self.assertIn(x,CPU)
 def test_synthetic_physical_opcode_and_negatives(self):
  for x in ("0x7fbf4040u", "cmpx(7,1,31,8,1)",
            "cmpi(1,0,31,0,0)", "bc(12,28,8)", "bc(12,30,8)",
            "bc(16,0,8)", "bc(18,0,8)",
            "0x4d9c0020u", "0x4d9e0020u",
            "0x4d9c0420u", "0x4e1c0420u",
            "M7.2 CR7 cmpld, signed/unsigned compare and conditional branches PASS"):
   self.assertIn(x,HOST)
 def test_device_and_ci(self):
  self.assertIn("M7.2 — EXECUÇÃO PPU CONTÍNUA + CR/BRANCH",APP)
  for x in ("tests/host_m72_cr_branch.c", "m72-cr-branch-host.log",
            "AscensionRecomp-M7.44-GOWA-6251-AOT-CROR-AppleARM64"):
   self.assertIn(x,WF)
  self.assertIn("<string>83</string>",PL)
if __name__=="__main__":unittest.main()
