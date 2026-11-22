"""Linux-only, synthetic NSO fixtures: validate source parity without game bytes."""
from __future__ import annotations
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path
import lz4.block

SRC = Path(__file__).resolve().parents[1] / "scripts" / "ktgl_reference_baseline.py"
spec = importlib.util.spec_from_file_location("fairy_ktgl_baseline", SRC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class SourceParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        size = max(end for _, _, end in m.CODE_REGIONS) + 0x4000
        original = bytearray(size)
        for at, raw, _ in m.WITNESSES:
            original[at:at + len(bytes.fromhex(raw))] = bytes.fromhex(raw)
        cls.original = bytes(original)
        cls.aot = cls.root / "main.patched.bin"
        cls.aot.write_bytes(cls.original + bytes(0x100))
        cls.profile = cls.root / "game.tsv"
        cls.profile.write_text(
            "title_id\t0100B9801F872000\npackage\tv458752\n"
            "sys_resource\t0x1000000\nmodules\tmain subsdk1 sdk\n")
        nso = bytearray(0x100)
        nso[:4] = b"NSO0"
        struct.pack_into("<I", nso, 0xC, 7)
        parts = ((0, cls.original),
                 (size + 0x1000, bytes(4096)),
                 (size + 0x3000, bytes(4096)))
        for idx, (mem, part) in enumerate(parts):
            enc = lz4.block.compress(part, store_size=False)
            off = len(nso)
            struct.pack_into("<III", nso, 0x10 + 16 * idx, off, mem, len(part))
            struct.pack_into("<I", nso, 0x60 + 4 * idx, len(enc))
            nso += enc
        cls.nso = cls.root / "main.nso"
        cls.nso.write_bytes(nso)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_aot_parity_of_both_resource_paths(self):
        result = m.audit(self.nso, self.aot, self.profile)
        self.assertEqual(len(result["critical_aarch64_regions"]), 10)
        self.assertEqual(len(result["guest_paths"]), 2)
        self.assertGreater(result["original_code_verified_bytes"], 4000)
        self.assertEqual([x["tested"] for x in result["references"]],
                         ["iPhone", "Mac, not iPhone", "iPhone"])
        self.assertTrue(result["not_a_gameplay_fix"])
        self.assertFalse(result["shader_rebuild"])
        self.assertFalse(result["ipa_built"])

    def test_fails_closed_on_modified_guest_reader(self):
        tampered = self.root / "bad_reader.bin"
        data = bytearray(self.aot.read_bytes())
        data[0xC11B60] ^= 1
        tampered.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "KTGL_chunk_direct_read"):
            m.audit(self.nso, tampered)

    def test_fails_closed_on_non_genuine_source(self):
        bad = self.root / "bad_nso"
        bad.write_bytes(b"NotAnNSO")
        with self.assertRaisesRegex(ValueError, "expected NSO0"):
            m.audit(bad, self.aot)

    def test_disambiguates_direct_from_event_driven(self):
        self.assertEqual(m.branch_target(self.original, 0xC10630), 0xC10690)
        self.assertEqual(m.branch_target(self.original, 0xC11924), 0xC10690)
        self.assertEqual({x[0] for x in m.CODE_REGIONS}.__contains__(
            "KTGL_chunk_direct_read"), True)

    def test_invalid_profile_must_not_be_reused(self):
        other = self.root / "other.tsv"
        other.write_text("title_id\t0100000000000000\npackage\tv458752\n"
                         "sys_resource\t0x1000000\n")
        with self.assertRaisesRegex(ValueError, "wrong title"):
            m.audit(self.nso, self.aot, other)

if __name__ == "__main__":
    unittest.main()
