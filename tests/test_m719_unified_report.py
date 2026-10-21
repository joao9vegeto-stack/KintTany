"""Launcher and truthful live-report source contracts."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class M719ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()

    def test_game_tab_has_one_execution_report_action(self):
        s=self.ui
        self.assertIn('self.nativeLaunchButton=[self arLauncherButton:@"INICIAR JOGO"',s)
        self.assertIn('self.ppuDiagnosticsButton=[self arLauncherButton:@"RELATÓRIO DA EXECUÇÃO"',s)
        self.assertEqual(s.count('[main addArrangedSubview:self.ppuDiagnosticsButton];'),1)
        self.assertIn('openUnifiedPpuMenu:',s)
        self.assertIn('self.nativeLaunchButton.enabled=enabled;',s)
        self.assertIn('self.hasGameInstallation && self.selectedElfData.length>0',s)

    def test_report_opens_before_a_run_and_during_execution(self):
        s=self.ui
        start=s.split('- (void)openUnifiedPpuMenu:',1)[1].split('- (void)shareAdvancedPpuReport:',1)[0]
        self.assertIn('[self openAdvancedPpuReport:sender];',start)
        report=s.split('- (void)openAdvancedPpuReport:',1)[1].split('- (NSString *)arUnifiedPpuText',1)[0]
        self.assertNotIn('if(!self.ppuReport.length&&!self.shaderBusy)return;',report)
        self.assertIn('details.text=[self arUnifiedPpuText];',report)
        self.assertIn('rightBarButtonItems=@[share,copy]',report)

    def test_report_uses_live_guest_evidence_and_states_limits(self):
        s=self.ui
        self.assertIn('NSString *report=[self arUnifiedPpuText];',s)
        self.assertIn('Chamadas de função AOT=%@',s)
        self.assertIn('cellFsOpen guest=%@ · opens OK=%@',s)
        self.assertIn('cellFsRead guest=%@ · bytes lidos pelo guest=%@',s)
        self.assertIn('chamadas HLE internas= NÃO INSTRUMENTADAS',s)
        self.assertIn('Leitura guest de arquivos do jogo= %@',s)
        self.assertIn('PSARC específico= NÃO MEDIDO',s)
        self.assertIn('Primeiro frame original= NÃO COMPROVADO',s)

    def test_export_live_utf8_report(self):
        s=self.ui
        self.assertIn('initForExportingURLs:@[url] asCopy:YES',s)
        self.assertIn('writeToURL:url atomically:YES',s)
        self.assertIn('encoding:NSUTF8StringEncoding',s)
        self.assertIn('AscensionRecomp-%@-NPUA80918-%@.txt',s)
        self.assertIn('UIPasteboard.generalPasteboard.string=report;',s)
        self.assertIn('initWithTitle:@"Compartilhar"',s)
        self.assertIn('initWithTitle:@"Copiar"',s)
        self.assertIn('action:@selector(shareAdvancedPpuReport:)',s)

if __name__=="__main__":
    unittest.main()
