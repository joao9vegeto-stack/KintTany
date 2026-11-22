"""Guarded Fairy Tail 2 KTGL arena allocation alignment patch."""
import sys, importlib.util, unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/"scripts/repack_align64.py"
sys.path.insert(0,str(SCRIPT.parent))
spec=importlib.util.spec_from_file_location("fairy2_align64",SCRIPT)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)
class AlignmentPatchTests(unittest.TestCase):
    def test_exact_guest_opcode_and_site(self):
        self.assertEqual(mod.ALIGN_SITE,0x21b6a74)
        self.assertEqual(mod.OLD_MOV.hex(),"02028052")
        self.assertEqual(mod.NEW_MOV.hex(),"2200a052")
        self.assertEqual(mod.NEW_ALIGN_BYTES,65536)
        self.assertEqual(mod.OLD_ALIGN_BYTES,16)
        self.assertEqual(mod.SOURCE_RUN,44981941022)
    def test_context_guard_rejects_invalid_build(self):
        raw=bytearray(mod.ALIGN_SITE+64)
        raw[mod.ALIGN_SITE:mod.ALIGN_SITE+4]=mod.OLD_MOV
        with self.assertRaisesRegex(RuntimeError,"fingerprint mismatch"):
            mod.patch_alignment_bytes(bytes(raw))
    def test_predecessor_patches_mandatory(self):
        self.assertIn("the previous 128MiB heap patch is missing",SCRIPT.read_text())
        self.assertIn("previous 3 GiB",SCRIPT.read_text())
        self.assertIn("five_region_cut_movs_preserved",SCRIPT.read_text())
        self.assertIn("heap128_mib_patch_preserved",SCRIPT.read_text())
    def test_compilers_not_invoked(self):
        src=SCRIPT.read_text()
        for x in ('run("xcodebuild"','run("dmsh_build.py"','run("build_ipa_from_nsp.py"'):
            self.assertNotIn(x,src)
