"""Synthetic-only HLE registry/coverage tests. Not gameplay compatibility."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from hle_coverage import handlers_from_source,audit
class HLETests(unittest.TestCase):
    def test_registry_and_gap(self):
        handlers=handlers_from_source('ps3_hle_register(0x1234ABCDu, "cellFoo", (void*)cellFoo);')
        r=audit([{'library':'cellFoo','nid':'0x1234abcd','stub':'0x1000'},
                 {'library':'cellSpurs','nid':'0x8888ffff','stub':'0x2000'}],handlers)
        self.assertEqual(r['registered_nids'],1)
        self.assertEqual(r['not_registered_nids'],1)
        self.assertEqual(r['missing_by_library']['cellSpurs'],1)
        self.assertIn('NOT proof',r['warning'])
    def test_registry_empty_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'no handler'):
            handlers_from_source('void none(void){}')
    def test_conflicting_registration_rejected(self):
        with self.assertRaisesRegex(ValueError,'both'):
            handlers_from_source('ps3_hle_register(0x11111111u, "A", (void*)A); ps3_hle_register(0x11111111u, "B", (void*)B);')
    def test_bad_import_rejected(self):
        with self.assertRaises(ValueError):audit([{'nid':'invalid','library':'x'}],{1:'x'})
    def test_duplicate_import_reported(self):
        r=audit([{'nid':'0x1','library':'a'},{'nid':'0x1','library':'a'}],{1:'a'})
        self.assertEqual(r['registered_nids'],1)
        self.assertEqual(len(r['duplicate_imports']),1)
if __name__=='__main__':unittest.main()
