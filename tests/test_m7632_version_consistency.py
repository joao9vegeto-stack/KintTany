"""Verify the release identity and the current launcher report contract."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class M7632(unittest.TestCase):
 def test_release(self):
  ui=(R/'ios/ARProbeApp.m').read_text()
  plist=(R/'ios/Probe-Info.plist').read_text()
  self.assertIn('<string>7.69.0</string>',plist)
  self.assertIn('static NSString *ARCurrentRelease(void)',ui)
  self.assertIn('App=%@ · title=NPUA80918 · origem=ELF autenticado no iPhone',ui)
  self.assertIn('AscensionRecomp-%@-NPUA80918-%@.txt',ui)
  self.assertNotIn('App=M7.61',ui)
  self.assertNotIn('Próximo PC pendente (híbrido)',ui)
 def test_guest_measurements(self):
  ui=(R/'ios/ARProbeApp.m').read_text()
  self.assertIn('Chamadas de função AOT=%@ · início(s) da entry=%@ · último PC=0x%08llX',ui)
  self.assertIn('cellFsOpen guest=%@ · opens OK=%@',ui)
  self.assertIn('Chamadas de função AOT=%@',ui)
  self.assertIn('Comandos RSX do jogo= %@',ui)
if __name__=='__main__':unittest.main()
