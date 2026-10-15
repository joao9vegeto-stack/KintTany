"""Import binding tests use synthetic metadata only."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_import_binder import ImportManifestError, parse_uint32, validate, generate
class ImportBinderTests(unittest.TestCase):
    def test_valid_manifest(self):
        rows=[{"stub":"0x10260","nid":"0x33","library":"cellSpurs"},
              {"stub":"0x10220","nid":"0x44","library":"sysPrxForUser"},
              {"stub":"0x10280","nid":"0x33","library":"cellSpurs"}]
        entries,report=validate(rows)
        self.assertEqual(report["stubs_validated"],3)
        self.assertEqual(report["unique_nids"],2)
        self.assertEqual(report["by_library"]["cellSpurs"],2)
        src=generate(entries)
        self.assertLess(src.index("0x00010220u"),src.index("0x00010260u"))
        self.assertEqual(src.count("ar_bind_import("),3)
    def test_duplicate_conflicting_address(self):
        with self.assertRaisesRegex(ImportManifestError,"duplicate"):
            validate([{"stub":"0x10000","nid":"0x111","library":"a"},
                      {"stub":"0x10000","nid":"0x222","library":"b"}])
    def test_null_misaligned(self):
        for address in ("0","0x10002"):
            with self.subTest(address=address):
                with self.assertRaises(ImportManifestError):
                    validate([{"stub":address,"nid":"0x1","library":"x"}])
    def test_bad_nid(self):
        for nid in (True,"0","0x100000000","not-nid"):
            with self.subTest(nid=nid):
                with self.assertRaises(ImportManifestError):
                    validate([{"stub":"0x1000","nid":nid,"library":"z"}])
    def test_zero_or_excessive(self):
        for rows in ([],[{"stub":4*i+0x1000,"nid":i+1,"library":"x"} for i in range(2049)]):
            with self.assertRaises(ImportManifestError):validate(rows)
