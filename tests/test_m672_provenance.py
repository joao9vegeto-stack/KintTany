from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
U=(R/"ios/ARProbeApp.m").read_text()
W=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
P=(R/"ios/Probe-Info.plist").read_text()
class Test(unittest.TestCase):
 def test_guard(self):
  for x in ("return -1007;","if(dest>UINT32_MAX || !lookup(d,len,ss,used,dest,4,1))",
            "return ar_ppu_bootstrap_fortyeight_trace(d,len,info,out,NULL);",
            "int ar_ppu_bootstrap_fortyeight_trace_m672(", "return m672_core(d,len,info,out,trace,NULL,NULL);"):
   self.assertIn(x,C)
 def test_snapshot(self):
  for x in ("const uint64_t prior_r12=gpr[12];","detail[0]=pc;detail[1]=w;",
            "detail[5]++;","detail[i+1u]=(uint32_t)value;",
            "m672_region(ss,used,va,4u,base"):
   self.assertIn(x,C)
 def test_ui_and_workflow(self):
  for x in ("ARCurrentRelease()","Copiar diagnóstico PPU",
            "ar_ppu_bootstrap_fortyeight_trace_m672(","r12 na leitura r0"):
   self.assertIn(x,U)
  for x in ("tests/host_m672_descriptor.c","m672-host.log","0.6.22-unsigned.ipa"):
   self.assertIn(x,W)
  self.assertIn("<string>7.68.0</string>",P)
  self.assertIn("<string>7680</string>",P)
if __name__=="__main__":unittest.main()
