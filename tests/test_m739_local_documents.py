"""M7.39 Documents-based PS3 game folder ingestion checks.

This is an independently testable workaround to inaccessible File Providers.
It never proves cellFsOpen/cellFsRead or RSX guest assets.
"""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]

class FolderLocalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.impl=(R/"ios/ARGameFolderStore.m").read_text()
  cls.header=(R/"ios/ARGameFolderStore.h").read_text()
  cls.ui=(R/"ios/ARProbeApp.m").read_text()
  cls.workflow=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  cls.plist=(R/"ios/Probe-Info.plist").read_text()
 def test_local_storage_access_is_first_class_no_cloud_picker(self):
  for value in ("ARGameFolderImportLocalDocuments", "ARGameFolderImportLocalAtURL",
                "NPUA80918", "Jogos", "Games", "USRDIR", "NSDocumentDirectory",
                "lstat(", "S_ISDIR", "ARGameFolderImport(folder"):
   self.assertIn(value,self.impl)
  self.assertIn("ARGameFolderImportLocalDocuments",self.header)
  self.assertIn("ARGameFolderImportLocalAtURL",self.header)
 def test_separate_button_exports_failure_and_success_to_unified_txt(self):
  for val in ("Detectar arquivos locais · NPUA80918",
              "importGameFolderFromDocuments:", "ARGameFolderImportLocalDocuments(&error)",
              "M7.50 F1 — PASTA LOCAL IMPORTADA",
              "M7.50 F1 — PASTA LOCAL NÃO ENCONTRADA",
              "self.folderReport=report", "Evento HOST Files separado",
              "@[rpcMarkerButton,localFolderButton,folderButton,elfButton]"):
   self.assertIn(val,self.ui)
 def test_real_host_proof_and_ios_files_entitlement(self):
  self.assertIn("tests/host_m739_local_documents.m",self.workflow)
  self.assertIn("m739-local-documents-host",self.workflow)
  self.assertIn("<key>UIFileSharingEnabled</key><true/>",self.plist)
  self.assertIn("<key>LSSupportsOpeningDocumentsInPlace</key><true/>",self.plist)
  self.assertIn("<string>7640</string>",self.plist)

if __name__=="__main__":unittest.main()
