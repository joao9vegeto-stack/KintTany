import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from elf_inventory import ELFError, inspect_elf, main

def fixture(machine=21, bits=64, malformed=False):
    if bits == 64:
        ehsize, phsize, paddr = 64, 56, 0x100
        hdr = struct.pack(">16sHHIQQQIHHHHHH", b"\x7fELF\x02\x02\x01" + bytes(9),
                          2, machine, 1, 0x10000, ehsize, 0, 0, ehsize, phsize, 1, 0, 0, 0)
        phdr = struct.pack(">IIQQQQQQ", 1, 5, paddr, 0x10000, 0, 4 if not malformed else 999, 0x1000, 16)
    else:
        ehsize, phsize, paddr = 52, 32, 0x100
        hdr = struct.pack(">16sHHIIIIIHHHHHH", b"\x7fELF\x01\x02\x01" + bytes(9),
                          2, machine, 1, 0, ehsize, 0, 0, ehsize, phsize, 1, 0, 0, 0)
        phdr = struct.pack(">IIIIIIII", 1, paddr, 0, 0, 4 if not malformed else 999, 0x1000, 5, 16)
    return hdr + phdr + bytes(paddr - len(hdr) - len(phdr)) + b"\x00\x01\x02\x03"

class TestInventory(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = Path(self.t.name)

    def tearDown(self):
        self.t.cleanup()

    def put(self, name, data):
        p = self.root / name
        p.write_bytes(data)
        return p

    def test_ppu64(self):
        obj = inspect_elf(self.put("EBOOT.ELF", fixture()))
        self.assertEqual(obj["e_machine"], 21)
        self.assertEqual(obj["elf_class"], 64)
        self.assertEqual(obj["load_segments"][0]["permissions"], "R-X")
        self.assertEqual(len(obj["sha256"]), 64)

    def test_spu32(self):
        obj = inspect_elf(self.put("spu.elf", fixture(machine=23, bits=32)))
        self.assertEqual((obj["elf_class"], obj["e_machine"]), (32, 23))

    def test_no_encrypted_self(self):
        with self.assertRaisesRegex(ELFError, "nao e ELF"):
            inspect_elf(self.put("EBOOT.BIN", b"SELF" + bytes(128)))

    def test_reject_out_of_range_segment(self):
        with self.assertRaisesRegex(ELFError, "fora dos limites"):
            inspect_elf(self.put("bad.elf", fixture(malformed=True)))

    def test_reject_wrong_machine(self):
        with self.assertRaisesRegex(ELFError, "arquitetura inesperada"):
            inspect_elf(self.put("x86.elf", fixture(machine=62)))

    def test_cli_metadata_only(self):
        ppu = self.put("EBOOT.ELF", fixture())
        spu = self.put("spu.elf", fixture(machine=23, bits=32))
        out = self.root / "report.json"
        self.assertEqual(main(["--elf", str(ppu), "--spu", str(spu), "--out", str(out)]), 0)
        data = json.loads(out.read_text())
        self.assertEqual(data["schema"], "ascension-recomp/inventory-v1")
        self.assertEqual(len(data["spu_modules"]), 1)
        self.assertNotIn("raw_bytes", str(data))

if __name__ == "__main__":
    unittest.main()
