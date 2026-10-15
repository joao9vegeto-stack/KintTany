"""All test words below are synthetic. No game code or user ELF is stored in Git."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from ppu_lift_probe import UnsupportedOpcode, lift_words, read_ppu_words
from make_synthetic_ppu import create_elf

class AotM21Tests(unittest.TestCase):
    def test_synthetic_ppu_from_elf(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "SYNTHETIC.ELF"
            f.write_bytes(create_elf())
            words = read_ppu_words(f, 0x10000, 16)
            src, names = lift_words(words, 0x10000)
            self.assertEqual(names, ["li", "bl", "blr"])
            self.assertIn("ctx->gpr[3]", src)
            self.assertIn("ar_guest_call(ctx, 0x10020ULL)", src)

    def test_common_instruction_group(self):
        # Artificial sequence tests lwz, stdu, std, ori, oris, extsw.
        words = [0x38400000, 0x64420001, 0x60420010, 0x80420004,
                 0xf821ff91, 0xf9c10000, 0x7c6307b4, 0x4e800020]
        source, names = lift_words(words, 0x20000)
        self.assertEqual(names, ["li", "oris", "ori", "lwz", "stdu", "std", "extsw", "blr"])
        self.assertIn("ar_write64", source)
        self.assertIn("ar_read32", source)

    def test_unknown_fails_closed(self):
        with self.assertRaisesRegex(UnsupportedOpcode, "unsupported"):
            lift_words([0xffffffff, 0x4e800020], 0x10000)

    def test_no_implicit_exit(self):
        with self.assertRaisesRegex(UnsupportedOpcode, "no blr"):
            lift_words([0x3860002a], 0x10000)

    def test_reject_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "BAD.ELF"
            f.write_bytes(bytes(100))
            with self.assertRaises(ValueError):
                read_ppu_words(f, 0x10000, 1)
