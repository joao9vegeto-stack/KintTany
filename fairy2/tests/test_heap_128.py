"""Fail-closed checks for Fairy Tail 2 heap patch on top of region-cut IPA."""
import importlib.util
import sys
import unittest
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "scripts" / "repack_heap_128.py"
sys.path.insert(0, str(FILE.parent))
sp = importlib.util.spec_from_file_location("fairy2_heap128", FILE)
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)

class Heap128Tests(unittest.TestCase):
    def test_arm64_exact_opcode(self):
        self.assertEqual(m.HEAP_SITE, 0x2295a88)
        self.assertEqual(m.OLD_MOV.hex(), "1328a052")
        self.assertEqual(m.NEW_MOV.hex(), "1300a152")
        self.assertEqual(m.OLD_HEAP_BYTES, 20 * 1024 * 1024)
        self.assertEqual(m.NEW_HEAP_BYTES, 128 * 1024 * 1024)
        self.assertEqual(m.SOURCE_RUN, 44980090949)

    def test_wrong_guest_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "main too short"):
            m.patch_heap_bytes(bytes(1024))
        bad = bytearray(m.HEAP_SITE + 64)
        bad[m.HEAP_SITE:m.HEAP_SITE+4] = m.OLD_MOV
        with self.assertRaisesRegex(RuntimeError, "fingerprint mismatch"):
            m.patch_heap_bytes(bytes(bad))

    def test_exactly_five_prior_region_movs_required(self):
        self.assertEqual(len(m.SITES), 5)
        self.assertEqual(len({s[0] for s in m.SITES}), 5)
        self.assertNotIn(m.HEAP_SITE, [s[0] for s in m.SITES])

    def test_no_compiler_or_romfs(self):
        src = FILE.read_text()
        self.assertNotIn('run("xcodebuild"', src)
        self.assertNotIn('run("dmsh_build.py"', src)
        self.assertNotIn('run("build_ipa_from_nsp.py"', src)
        self.assertIn("check_framework(tmp_game, proof)", src)
