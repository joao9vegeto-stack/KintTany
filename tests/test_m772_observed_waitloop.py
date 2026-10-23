import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import m772_unpack_ci


class ObservedWaitloopProbeTest(unittest.TestCase):
    def test_exact_usleep_waitloop_hook_is_added_once(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp)
            ppu = source / "ppu"
            ppu.mkdir()
            unit = ppu / "ppu_recomp_001.cpp"
            unit.write_text(
                "void func_00419AC8(ppu_context* ctx) {\n"
                "loc_00419D1C:\n"
                "    vm_read32(ctx);\n"
                "    sys_timer_usleep(ctx);\n"
                "}\n"
                "void func_00419E00(ppu_context* ctx) {\n}\n"
            )

            self.assertEqual(m772_unpack_ci.instrument_known_waitloop(source), 1)
            first = unit.read_text()
            self.assertEqual(first.count("ar_m772_note_hotloop(0x00419D1Cu, ctx);"), 1)
            self.assertLess(first.index("loc_00419D1C:"),
                            first.index("ar_m772_note_hotloop(0x00419D1Cu, ctx);"))

            self.assertEqual(m772_unpack_ci.instrument_known_waitloop(source), 1)
            self.assertEqual(unit.read_text(), first)


if __name__ == "__main__":
    unittest.main()
