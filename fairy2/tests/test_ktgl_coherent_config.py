"""Regression gates for restoring the ORIGINAL KTGL shared-config read model."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(ROOT))
import repack_full_resource_va as root
import repack_ktgl_coherent_config as consistent

class CoherentKtglTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Structurally identical to the source section's 5GiB root pre-patch
        # layout: original RX + writable image + executable x1 zero cave.
        cls.source=bytearray(root.CAVE_LAST)
        for site,reg in root.ROOT_SITES:
            cls.source[site:site+4]=root.ROOT_OLD[reg]
        for site,opcode in root.PRESERVE:
            cls.source[site:site+4]=bytes.fromhex(opcode)
        cls.root,cls.stamp=root.patch_bytes(bytes(cls.source))
        cls.coherent,cls.proof=consistent.coherent_patch(cls.root,cls.stamp)

    def test_root_5g_and_shared_ktgl_config_both_coherent(self):
        self.assertEqual(self.stamp["trampoline_count"],5)
        self.assertEqual(consistent.CAPACITY_BYTES,0x80000000)
        self.assertEqual(consistent.CAPACITY_UNITS,0x20000000)
        b=self.coherent
        self.assertEqual(b[consistent.OLD_SITE:consistent.OLD_SITE+4],
                         root.branch_opcode(consistent.OLD_SITE,consistent.STUB_AT))
        self.assertEqual(b[consistent.SECOND:consistent.SECOND+4],
                         consistent.ORIGINAL_SECOND)
        self.assertEqual(b[consistent.STUB_AT:consistent.STUB_AT+4],
                         consistent.STUB_MOVZ)
        self.assertEqual(b[consistent.STUB_AT+4:consistent.STUB_AT+8],
                         consistent.STORE_CAP)
        self.assertEqual(b[consistent.STUB_AT+8:consistent.STUB_AT+12],
                         root.branch_opcode(consistent.STUB_AT+8,
                                            consistent.OLD_SITE+4))
        self.assertTrue(self.proof["no_inflator_or_direct_reader_brk"])
        self.assertEqual(self.proof["guest_instruction_changes_after_5g"],5)

    def test_only_five_expected_words_differ_from_verified_root(self):
        changed=[p for p in range(0,len(self.root),4)
                 if self.root[p:p+4]!=self.coherent[p:p+4]]
        self.assertEqual(changed,[consistent.OLD_SITE,consistent.SECOND,
                                  consistent.STUB_AT,consistent.STUB_AT+4,
                                  consistent.STUB_AT+8])
        self.assertEqual(
            hashlib.sha256(self.root[0x22d4000:root.PATCH_OFF]).hexdigest(),
            hashlib.sha256(self.coherent[0x22d4000:root.PATCH_OFF]).hexdigest())
        for site,reg in root.ROOT_SITES:
            index=list(root.ROOT_SITES).index((site,reg))
            cave=root.CAVE+index*root.CAVE_STRIDE
            self.assertEqual(self.root[site:site+4],
                             self.coherent[site:site+4])
            self.assertEqual(self.root[cave:cave+12],
                             self.coherent[cave:cave+12])

    def test_refuse_dirty_executable_code_cave(self):
        b=bytearray(self.root)
        b[consistent.STUB_AT]=0x42
        with self.assertRaisesRegex(RuntimeError,"contains code/data"):
            consistent.coherent_patch(bytes(b),self.stamp)

    def test_refuse_unpinned_original_dynamic_site(self):
        b=bytearray(self.root)
        b[consistent.SECOND:consistent.SECOND+4]=consistent.ORIGINAL_SECOND
        with self.assertRaisesRegex(RuntimeError,"KNOWN incorrect fixed-size"):
            consistent.coherent_patch(bytes(b),self.stamp)

    def test_fixed_2g_is_necessity_not_proof_of_device_boot(self):
        self.assertEqual(self.proof["new_capacity_bytes"],2**31)
        self.assertTrue(self.proof["not_verified_on_device"])
        self.assertIn("config",self.proof["new_one_shared_source"])
        for key in ("no_bypass_of_original_g1t_g1s_parsers",
                    "no_inflator_or_direct_reader_brk"):
            self.assertTrue(self.proof[key])

if __name__=="__main__":
    unittest.main()
