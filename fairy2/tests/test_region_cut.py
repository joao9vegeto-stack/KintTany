"""Fairy2iOS 60GiB allocator cut: fail-closed regression gate."""
import importlib.util
import sys,unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/"scripts/repack_region_cut.py"
spec=importlib.util.spec_from_file_location("fairy2_region_cut",SCRIPT)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
class RegionCut(unittest.TestCase):
    def test_budget(self):
        self.assertEqual(m.OLD_REGION,60*1024**3)
        self.assertEqual(m.NEW_REGION,3*1024**3)
        self.assertLess(m.NEW_REGION+m.NODE_AREA,m.ALIAS)
    def test_exact_sites(self):
        self.assertEqual(len(m.SITES),5)
        self.assertEqual(len({s[0] for s in m.SITES}),5)
        for _,before,after,signature in m.SITES:
            self.assertEqual(len(bytes.fromhex(before)),4)
            self.assertEqual(len(bytes.fromhex(after)),4)
            self.assertEqual(len(signature),64)
    def test_wrong_code_rejected(self):
        n=max(x[0] for x in m.SITES)+64
        with self.assertRaisesRegex(RuntimeError,"unknown ARM64"):
            m.transform_main(bytes(n))
        raw=bytearray(n)
        for off,orig,_,_ in m.SITES: raw[off:off+4]=bytes.fromhex(orig)
        with self.assertRaisesRegex(RuntimeError,"fingerprint mismatch"):
            m.transform_main(raw)
    def test_no_compiler_call(self):
        txt=SCRIPT.read_text()
        for forbidden in ('run("xcodebuild"','run("dmsh_build.py"','run("build_ipa_from_nsp.py"'):
            self.assertNotIn(forbidden,txt)
        self.assertIn("validate_guest_region_patch(zip_macho,region_stamp)",txt)
