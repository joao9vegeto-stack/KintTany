import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from self_inventory import inspect, SelfInventoryError

def fixture():
    d = bytearray(0x400)
    struct.pack_into(">IIHHIQQ", d, 0, 0x53434500, 2, 0x1c, 1, 0x220, 0x300, 0x1000)
    struct.pack_into(">9Q", d, 0x20, 3, 0x70, 0x90, 0xd0, 0x200, 0x170, 0, 0x190, 0x90)
    struct.pack_into(">QIIQQ", d, 0x70, 0x1010000001000003, 0x1000002, 8, 0, 0)
    struct.pack_into(">16sHHIQQQIHHHHHH", d, 0x90,
                     b"\x7fELF\x02\x02\x01\x66" + bytes(8), 2, 21, 1,
                     0x10000, 64, 0, 0, 64, 56, 1, 64, 0, 0)
    struct.pack_into(">IIQQQQQQ", d, 0xd0, 1, 0x400005, 0, 0x10000, 0x10000, 32, 32, 16)
    struct.pack_into(">QQIIQ", d, 0x170, 0x300, 16, 1, 0, 1)
    struct.pack_into(">IIQ", d, 0x190, 3, 0x90, 0)
    d[0x1a0:0x1a4] = b"NPD\x00"
    struct.pack_into(">III", d, 0x1a4, 1, 2, 0)
    d[0x1b0:0x1b0+36] = b"UP9000-NPUA80918_00-GOWADIGITALVERS1"
    return bytes(d)

class SelfInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "SAMPLE.SELF"
    def tearDown(self):
        self.temp.cleanup()
    def write(self, data):
        self.path.write_bytes(data)
        return self.path
    def test_retail_npdrm_local(self):
        x = inspect(self.write(fixture()))
        self.assertEqual(x["npdrm"]["content_id"], "UP9000-NPUA80918_00-GOWADIGITALVERS1")
        self.assertEqual(x["npdrm"]["license_type"], 2)
        self.assertTrue(x["sce"]["retail_encrypted"])
        self.assertFalse(x["decryption_performed"])
    def test_bad_magic(self):
        d = bytearray(fixture()); d[:4] = b"FAIL"
        with self.assertRaises(SelfInventoryError):
            inspect(self.write(d))
    def test_bad_segment_range(self):
        d = bytearray(fixture())
        struct.pack_into(">Q", d, 0x170, 0x3fa)
        with self.assertRaises(SelfInventoryError):
            inspect(self.write(d))
    def test_wrong_cpu(self):
        d = bytearray(fixture())
        struct.pack_into(">H", d, 0x90 + 18, 62)
        with self.assertRaises(SelfInventoryError):
            inspect(self.write(d))
