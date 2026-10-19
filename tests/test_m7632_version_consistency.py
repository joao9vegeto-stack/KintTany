"""Verify M7.63.2 installed version / UI / diagnostic separation."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class M7632(unittest.TestCase):
 def test_release(self):
  ui=(R/'ios/ARProbeApp.m').read_text()
  plist=(R/'ios/Probe-Info.plist').read_text()
  self.assertIn('<string>7.63.2</string>',plist)
  self.assertIn('static NSString *ARCurrentRelease(void)',ui)
  self.assertIn('App=%@ (CFBundleVersion=%@)',ui)
  self.assertIn('AscensionRecomp-%@-NPUA80918-%@.txt',ui)
  self.assertNotIn('App=M7.61',ui)
  self.assertNotIn('Próximo PC pendente (híbrido)',ui)
 def test_guest_measurements(self):
  ui=(R/'ios/ARProbeApp.m').read_text()
  self.assertIn('Sem ARM64 registrado; dispatcher=%d (NÃO é fallback)',ui)
  self.assertIn('Guest FS: open=%u · read=%u · bytes=%llu',ui)
  self.assertIn('DELTA FÍSICO vs M7.63.1:',ui)
  self.assertIn('RSX do Ascension: não demonstrado',ui)
if __name__=='__main__':unittest.main()
