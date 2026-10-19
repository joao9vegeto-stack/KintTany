"""M7.18 tests use fabricated symbol tables; never include game C/ELF."""
from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("bulk_verify",ROOT/"tools/verify_m718_macho.py")
verify_mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_mod)

class M718BulkTests(unittest.TestCase):
    def test_exact_500_native_symbols(self):
        names=[f"ar_bulk_ppu_{x:08x}" for x in range(4,2004,4)]
        self.assertEqual(len(names),500)
        fake="".join(f"0000000000001000 T _{n}\n" for n in names)
        self.assertEqual(verify_mod.verify(fake,names,500),500)
        with self.assertRaises(ValueError):
            verify_mod.verify(fake[:-40],names,500)
        with self.assertRaises(ValueError):
            verify_mod.verify(fake.replace(" T _"," U _",1),names,500)
        with self.assertRaises(ValueError):
            verify_mod.verify(fake,names[:-1],500)
    def test_strict_owner_elf_gate_and_private_secret_boundary(self):
        staging=(ROOT/"tools/stage_m718_bulk.py").read_text()
        bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        script=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        self.assertIn("4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5",staging)
        self.assertIn("621a811560e5e6f5f921f2099088879e64fb3850c68dec3b4828f8ebedfad9d1",staging)
        self.assertIn("ar_bulk_install_sha256(digest,sizeof(digest))",bridge)
        self.assertIn("ASCENSION_PRIVATE_BULK_AOT_LINKED",bridge)
        self.assertIn("ASCENSION_PRIVATE_BULK_C",script)
        self.assertIn("_ar_bulk_install_sha256$",script)
        self.assertIn("tools/verify_m718_macho.py",script)
        self.assertIn("ASCENSION_PRIVATE_AOT_C",script)
        self.assertNotIn("GOWA.ELF",str(ROOT/"tools/stage_m718_bulk.py"))
    def test_remaining_native_status_remains_precise(self):
        ui=(ROOT/"ios/ARProbeApp.m").read_text()
        self.assertIn("ASCENSIONRECOMP %@",ui)  # current milestone header; M7.18 AOT guarded separately
        self.assertIn("RSX do Ascension: não demonstrado",ui)
        self.assertIn("Entradas AOT vinculadas: %u",ui)

if __name__=="__main__":unittest.main()
