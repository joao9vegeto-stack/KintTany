"""M6.7.3: checked import NID lookup, no fake HLE or arbitrary branch."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
U=(R/"ios/ARProbeApp.m").read_text()
W=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
P=(R/"ios/Probe-Info.plist").read_text()
class TestM673(unittest.TestCase):
 def test_reader(self):
  for token in ('int ar_private_import_match(', '0x60000002u',
                '0x1b434cecu','const uint8_t*pt=lookup(',
                'const uint8_t*pn=lookup(','result[0]=found_nid;',
                'return -1007;'):
   self.assertIn(token,C)
 def test_ui_privacy(self):
  for token in ('if(rc48==-1007 && detail48[10]==2u',
                'ar_private_import_match(', 'ASCENSIONRECOMP   ·   M7.11',
                'Importação identificada, MAS serviço HLE ainda NÃO vinculado',
                'Copiar diagnóstico PPU'):
   self.assertIn(token,U)
 def test_ci(self):
  for token in ('tests/host_m673_import_match.c','m673-import-host.log',
                'AscensionRecomp-M7.49-GOWA-6251-AOT-FRSP-AppleARM64'):
   self.assertIn(token,W)
  self.assertIn('<string>89</string>',P)
if __name__=="__main__":unittest.main()
