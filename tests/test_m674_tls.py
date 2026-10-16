from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
U=(R/"ios/ARProbeApp.m").read_text()
W=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
P=(R/"ios/Probe-Info.plist").read_text()
class TLS(unittest.TestCase):
 def test_hle_dispatch(self):
  for x in ('int ar_ppu_bootstrap_fortyeight_trace_m674(',
            'ar_private_import_match(', 'match[0]==0x744680a2u',
            'strcmp(lib,"sysPrxForUser")==0',
            'return -1007; /* other invalid jumps remain forbidden */'):
   self.assertIn(x,C)
 def test_checked_memory(self):
  for x in ('#define AR_TLS_SPACE 65536u',
            '#define AR_TLS_MAX 16384u',
            'm65_read_guest(d,len,s,n,m,stack,sb,src+i,1u,&value)',
            'gpr[13]=AR_TLS_START+0x7000u',
            'return m672_core(d,len,info,out,trace,NULL,NULL);',
            'return m672_core(d,len,info,out,trace,detail,NULL);'):
   self.assertIn(x,C)
 def test_report_and_ci(self):
  for x in ('ASCENSIONRECOMP   ·   M6.7.6',
            'ar_ppu_bootstrap_fortyeight_trace_m674(',
            'TLS HLE M6.7.6:',
            'sys_initialize_tls HLE executada'):
   self.assertIn(x,U)
  for x in ('tests/host_m674_tls.c',
            'm674-tls-host.log',
            'AscensionRecomp-M6.7.6-mtlr-guarded-blr'):
   self.assertIn(x,W)
  self.assertIn('<string>70</string>',P)
if __name__=="__main__":unittest.main()
