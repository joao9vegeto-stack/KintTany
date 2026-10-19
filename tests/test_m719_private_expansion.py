"""M7.19: strict 850-entry bulk2 link and staging interface contract.

All test symbols are synthetic. Owner ELF and generated AOT C are NEVER
stored in public Git or test archives.
"""
from __future__ import annotations
from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[1]
def loader(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

verify=loader("m719_verify","tools/verify_m719_macho.py")
stage=loader("m719_stage","tools/stage_m719_bulk2.py")

class BulkM719Tests(unittest.TestCase):
    def test_850_genuine_native_symbol_definitions_required(self):
        names=[f"ar_bulk2_ppu_{i:08x}" for i in range(0x1000,0x1000+4*850,4)]
        elf_macho="".join(f"0000000000001000 T _{n}\n" for n in names)
        self.assertEqual(verify.verify(elf_macho,names,850),850)
        with self.assertRaises(ValueError):
            verify.verify(elf_macho,names[:-1],850)
        with self.assertRaises(ValueError):
            verify.verify(elf_macho.replace(" T _"," U _",1),names,850)
        with self.assertRaises(ValueError):
            verify.verify(elf_macho,names,500)

    def test_secret_authentication_and_prior_manifests_are_required(self):
        self.assertEqual(stage.COUNT,850)
        self.assertEqual(stage.ELF_SHA256,
                         "4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5")
        self.assertEqual(stage.SOURCE_SHA256,
                         "a81a67cfb4be91919f5043a226ffb5c25cefce4c9d663d3dcdca65b8831fdfc7")
        with self.assertRaises(ValueError):
            stage.decode("garbage")
        with self.assertRaises(ValueError):
            stage.decode("a"*48001)
        self.assertIn("002c16a4",stage.REQUIRED)
        self.assertIn("002c16b4",stage.REQUIRED)
        self.assertIn("003c5cc8",stage.REQUIRED)

    def test_preserve_568_linked_old_AOT_no_fake_gameplay(self):
        bridge=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        builder=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        ui=(ROOT/"ios/ARProbeApp.m").read_text()
        workflow=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
        self.assertIn("ar_private_aot_install_sha256(digest,sizeof(digest))",bridge)
        self.assertIn("ar_bulk_install_sha256(digest,sizeof(digest))",bridge)
        self.assertIn("ar_bulk2_install_sha256(digest,sizeof(digest))",bridge)
        self.assertIn("verify_m712_macho.py",builder)
        self.assertIn("verify_m718_macho.py",builder)
        self.assertIn("verify_m719_macho.py",builder)
        self.assertIn("ASCENSION_PRIVATE_BULK2_AOT_LINKED",builder)
        self.assertIn("ASCENSION_AOT_BULK2_GZIP_B64",workflow)
        self.assertIn("ASCENSIONRECOMP %@",ui)  # current experimental stage label
        self.assertIn("RSX do Ascension: não demonstrado",ui)

if __name__=="__main__":
    unittest.main()
