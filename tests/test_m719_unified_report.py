"""M7.19 report UX: one visible option, complete content, Files TXT export.

Static UI regression tests work in GitHub Actions without simulator or game ELF.
"""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class M719ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()

    def test_one_diagnostic_button_visible_on_game_tab(self):
        s=self.ui
        self.assertIn('[stack addArrangedSubview:diagnostics];',s)
        self.assertEqual(s.count('[stack addArrangedSubview:diagnostics];'),1)
        self.assertNotIn('[stack addArrangedSubview:reportButton];',s)
        self.assertNotIn('[stack addArrangedSubview:batchButton];',s)
        self.assertNotIn('[stack addArrangedSubview:advancedButton];',s)
        self.assertIn('Relatório completo · visualizar / TXT',s)
        self.assertIn('self.ppuDiagnosticsButton.enabled=NO;',s)
        self.assertEqual(s.count('self.ppuDiagnosticsButton.enabled=(self.ppuReport.length>0);'),2)

    def test_complete_report_keeps_real_native_and_ppc_evidence(self):
        s=self.ui
        self.assertIn('NSString *body=self.ppuReport.length?self.ppuReport:self.ppuSummary;',s)
        self.assertIn('self.ppuReport=[NSString stringWithFormat:@"%@\\n\\n%@",self.ppuSummary,extended];',s)
        self.assertIn('self.ppuReport=[self.ppuReport stringByAppendingString:frontierReport];',s)
        self.assertIn('[extended appendString:frontierReport];',s)
        self.assertIn('AOT_EXEC 0x%08X',s)
        self.assertIn('CALL_CANDIDATE 0x%08X',s)
        self.assertIn('PPC somente leitura',s)
        self.assertIn('RSX do Ascension: não demonstrado',s)

    def test_export_real_utf8_txt_and_copy_all(self):
        s=self.ui
        self.assertIn('initForExportingURLs:@[url] asCopy:YES',s)
        self.assertIn('writeToURL:url atomically:YES',s)
        self.assertIn('encoding:NSUTF8StringEncoding',s)
        self.assertIn('AscensionRecomp-M7.53-NPUA80918-%@.txt',s)
        self.assertIn('UIPasteboard.generalPasteboard.string=report;',s)
        self.assertIn('Compartilhar TXT · direto ao ChatGPT',s)
        self.assertIn('Visualizar relatório',s)
        self.assertIn('Copiar tudo',s)
        self.assertIn('popover.sourceView=sender',s)
        self.assertIn('Relatório sem bytes de ELF, PSARC ou arquivos comerciais.',s)
        self.assertIn('EXECUÇÃO ATUAL',s)
        self.assertIn('COMPARAÇÃO COM A BUILD ANTERIOR',s)

if __name__=="__main__":
    unittest.main()
