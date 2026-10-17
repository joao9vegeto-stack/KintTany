"""M7.3: inspect second actual PS3 import at fail-closed bctrl; no fake HLE."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
CPU=(R/"ios/ARNativePPUContinuous.c").read_text()
BR=(R/"ios/ARLivePPUContinuous.c").read_text()
UI=(R/"ios/ARProbeApp.m").read_text()
HOST=(R/"tests/host_m73_import_discovery.c").read_text()
WF=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
P=(R/"ios/Probe-Info.plist").read_text()
class TestSecondImport(unittest.TestCase):
 def test_stops_and_reads_authentic_metadata(self):
  for a in ('if(evidence && rc==-1314 && trace[2]==0x4e800421u)',
            'const uint64_t stub=cpu.gpr[12];',
            'ar_private_import_match(d,len,(uint32_t)stub,match,local_library)',
            'if(code_staged)', 'evidence[6]=match[0];',
            'evidence[8]|=1u;', 'evidence[8]|=2u;',
            'evidence[8]|=4u;', 'evidence[8]|=8u;',
            'if((evidence[8]&15u)==15u)evidence[8]|=16u;',
            'ar_bridge_shutdown();'):
   self.assertIn(a,BR)
 def test_legacy_abi_and_no_fake_hle(self):
  for a in ('int ar_m71_private_continuous_probe(',
            'int ar_m73_private_import_probe(',
            'return ar_continuous_core(d,len,guest_stub,budget,out,NULL,NULL);',
            'if(!evidence||!library)return -1320;'):
   self.assertIn(a,BR)
  self.assertIn('rc=-1314;fail_ea=target;break;',CPU)
  self.assertNotIn('ar_bind_hle(match[0]',BR)
 def test_native_host_two_imports(self):
  for a in ('0xABCDEF01u','0x10080u', 'p16(d,0x2e6,2u);',
            'out[1]!=18u','evidence[8]!=31u',
            'evidence[6]!=0xABCDEF01u',
            'strcmp(library,"sysPrxForUser")!=0',
            'M7.3 real second PRX stub library NID identified, unknown HLE blocked PASS'):
   self.assertIn(a,HOST)
 def test_ui_ci_version(self):
  for a in ('M7.3 — IMPORTAÇÃO PRX NA PARADA REAL',
            'r12/stub candidato=', 'PRX status=%d',
            'ar_m73_private_import_probe(', 'Somente leitura:',
            'Copiar diagnóstico PPU'):
   self.assertIn(a,UI)
  for a in ('tests/host_m73_import_discovery.c','m73-prx-host.log',
            'AscensionRecomp-M7.25-PPC-call-origin',
            '_ar_m73_private_import_probe'):
   self.assertIn(a,WF)
  self.assertIn('<string>74</string>',P)
if __name__=="__main__": unittest.main()
