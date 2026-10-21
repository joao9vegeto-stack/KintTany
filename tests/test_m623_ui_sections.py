import unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]
S=(P/"ios/ARProbeApp.m").read_text()
class OrganizedUI(unittest.TestCase):
 def test_groups_scroll_and_actions(self):
  for t in ('initWithItems:@[@"JOGAR",@"CONFIGURAÇÕES"]',
            'arSwitchTab:', 'self.gameList.hidden=!showGame',
            'self.graphicsList.hidden=showGame','page.contentLayoutGuide',
            'page.frameLayoutGuide','self.nativeLaunchButton=',
            'SELECIONAR PASTA NPUA80918','USAR PASTA EM DOCUMENTOS',
            'importM59ELF:','testM58AlphaTest:','testM57BlendMask:',
            'testM56StencilBitmasks:','testM55StencilMask:',
            'testM54DepthOcclusion:','testM53Multipass:',
            'testM52TextureMutation:','testM51GuestDraw:',
            'testGuestRSXShader:','testRSXCache:'):
   self.assertIn(t,S)
 def test_real_ppu_is_preserved(self):
  bridge=(P/"ios/ARLivePPUBridge.c").read_text()
  self.assertIn('ar_m772_run_entry(&ctx,image.entry_code)',bridge)
  self.assertIn('ENTRY AOT EM EXECUÇÃO',S)
  start=S.rsplit('- (void)startNativeGame:(UIButton*)sender {',1)[1].split('- (void)nativeRunRefreshTick:',1)[0]
  self.assertIn('ar_m70_native_runtime_probe(elf.bytes,elf.length,0u,native)',start)
  self.assertNotIn('ARGameFolderRestore(',start)
  self.assertIn('NSThread *worker=[[NSThread alloc] initWithBlock:',start)
  self.assertIn('worker.name=@"Ascension PS3Recomp guest";',start)
  self.assertIn('worker.stackSize=(NSUInteger)64u*1024u*1024u;',start)
  self.assertIn('[worker start];',start)
  self.assertIn('Acesso à pasta do jogo expirou ou foi revogado.',start)
  self.assertIn('FALHA NO HOST / LOADER',S)
  self.assertNotIn('ar_ppu_bootstrap_',start)
 def test_version(self):
  self.assertIn("7.69.0",(P/"ios/Probe-Info.plist").read_text())
  self.assertIn("AscensionRecompProbe-0.6.22-unsigned.ipa",
      (P/"tools/build_ios_probe_ipa.sh").read_text())
if __name__=="__main__":unittest.main()
