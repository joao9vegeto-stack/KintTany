import unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]
S=(P/"ios/ARProbeApp.m").read_text()
class OrganizedUI(unittest.TestCase):
 def test_groups_scroll_and_actions(self):
  for t in ('initWithItems:@[@"Jogo / PPU", @"RSX / Metal"]',
            'arSwitchTab:', 'self.gameList.hidden=!showGame',
            'self.graphicsList.hidden=showGame','scroll.contentLayoutGuide',
            'scroll.frameLayoutGuide','[NSLayoutConstraint deactivateConstraints:old]',
            'importM59ELF:','testM58AlphaTest:','testM57BlendMask:',
            'testM56StencilBitmasks:','testM55StencilMask:',
            'testM54DepthOcclusion:','testM53Multipass:',
            'testM52TextureMutation:','testM51GuestDraw:',
            'testGuestRSXShader:','testRSXCache:'):
   self.assertIn(t,S)
 def test_real_ppu_is_preserved(self):
  for t in ('M6.2 PPU REAL 16/16: OK',
            'M5.9 NPUA80918: ELF REAL VALIDADO',
            'M6.2: registradores ou pilha divergentes'):
   self.assertIn(t,S)
 def test_version(self):
  self.assertIn("7.66.0",(P/"ios/Probe-Info.plist").read_text())
  self.assertIn("AscensionRecompProbe-0.6.22-unsigned.ipa",
      (P/"tools/build_ios_probe_ipa.sh").read_text())
if __name__=="__main__":unittest.main()
