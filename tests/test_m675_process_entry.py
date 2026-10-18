"""M6.7.5: process entry must supply real PT_TLS before guest CRT dispatch."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
C=(ROOT/"ios/ARPrivateELFProbe.c").read_text()
U=(ROOT/"ios/ARProbeApp.m").read_text()
W=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
T=(ROOT/"tests/host_m675_process_entry.c").read_text()
P=(ROOT/"ios/Probe-Info.plist").read_text()
class PS3ProcessEntry(unittest.TestCase):
 def test_real_elf_pt_tls(self):
  for token in ('static int ar_m675_entry_tls(', 'if(b32(p)!=7u)continue;',
                'const uint64_t va=b64(p+16),filesz=b64(p+32),memsz=b64(p+40);',
                'if(filesz && !lookup(', 'return -1021;'):
   self.assertIn(token,C)
 def test_entry_registers_are_seeded_once(self):
  for token in ('gpr[7]=entry[0];gpr[8]=entry[1];',
                'gpr[9]=entry[2];gpr[10]=entry[3];',
                'gpr[12]=0x00100000u;', 'tls_record[9]=has_tls;',
                'tls_record[11]=(uint32_t)gpr[12];',
                'if(tls_record){'):
   self.assertIn(token,C)
  self.assertNotIn('gpr[3]=entry[0]',C)
  self.assertNotIn('gpr[4]=entry[1]',C)
 def test_safe_tls_hle_and_regressions(self):
  for token in ('match[0]==0x744680a2u',
                'strcmp(lib,"sysPrxForUser")==0',
                'return -1007; /* other invalid jumps remain forbidden */',
                'ar_tls_initialize(d,len,ss,used,&guest,stack,base,'):
   self.assertIn(token,C)
  for token in ('0x60e30000u', '0x61040000u',
                '0x61250000u', '0x61460000u',
                'p32(d,tlsph,7u);',
                'M6.7.5 ELF PT_TLS process-entry ABI and negative tests PASS'):
   self.assertIn(token,T)
 def test_ui_build(self):
  for token in ('ASCENSIONRECOMP   ·   M7.11',
                'Entrada LV2: PT_TLS presente=',
                'ar_ppu_bootstrap_fortyeight_trace_m674('):
   self.assertIn(token,U)
  for token in ('tests/host_m675_process_entry.c',
                'm675-entry-host.log',
                'AscensionRecomp-M7.45-GOWA-6251-AOT-SRW-AppleARM64'):
   self.assertIn(token,W)
  self.assertIn('<string>84</string>',P)
if __name__=="__main__":unittest.main()
