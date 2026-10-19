"""M7.36: persistent TXT + share sheet without forcing iCloud Drive."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
class M736ShareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui=(ROOT/"ios/ARProbeApp.m").read_text()
        cls.plist=(ROOT/"ios/Probe-Info.plist").read_text()
        cls.script=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
    def test_direct_share_instead_of_forced_icloud(self):
        for token in (
            "arCreatePpuTextFile", "NSDocumentDirectory",
            "initWithActivityItems:@[url] applicationActivities:nil",
            "Compartilhar TXT · direto ao ChatGPT",
            "Salvar TXT · Arquivos", "picker.directoryURL=nil",
            "initForExportingURLs:@[url] asCopy:YES",
            "UIActivityViewController",
        ):
            self.assertIn(token,self.ui)
        self.assertNotIn("[NSTemporaryDirectory() stringByAppendingPathComponent:name]",self.ui)
    def test_files_shares_app_documents_and_version(self):
        self.assertIn("<key>UIFileSharingEnabled</key><true/>",self.plist)
        self.assertIn("<key>LSSupportsOpeningDocumentsInPlace</key><true/>",self.plist)
        self.assertIn("<string>0.6.22</string>",self.plist)
        self.assertIn("<string>90</string>",self.plist)
        self.assertIn("AscensionRecomp-M7.58-NPUA80918",self.ui)
        self.assertIn("AscensionRecompProbe-0.6.22-unsigned.ipa",self.script)
    def test_owner_elf_and_guest_fallback_separate(self):
        c=(ROOT/"runtime/ppu_m736_native_time.c").read_text()
        fallback=(ROOT/"runtime/ppu_m720_fallback.c").read_text()
        boot=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        self.assertIn("ar_m736_register_owner",c)
        self.assertIn("ar_m712_exec_window",c)
        self.assertIn("case 75:{ /* M7.36 mulhw",fallback)
        self.assertIn("ar_m736_register_owner(d,len)",boot)
        self.assertIn("return -45;",boot)

if __name__=="__main__":
    unittest.main()
