"""Synthetic SELF and SFO fixtures: no commercial code."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from package_preflight import PreflightError, inventory, read_self, read_sfo

def fake_self():
    obj = bytearray(0x400)
    obj[:4] = b'SCE\x00'
    obj[0x90:0xa0] = b'\x7fELF\x02\x02\x01\x66' + bytes(8)
    struct.pack_into('>HHIQQQIHHHHHH', obj, 0xa0, 2, 21, 1, 0x20088, 64, 0, 0, 64, 56, 3, 0, 0, 0)
    return bytes(obj)

def fake_sfo():
    rows = [('TITLE_ID', 0x0204, b'NPUA80918\x00'), ('TITLE', 0x0204, b'God of War: Ascension\x00'), ('VERSION', 0x0204, b'01.00\x00')]
    key = b''
    val = b''
    table = b''
    for k, typ, v in rows:
        table += struct.pack('<HHIII', len(key), typ, len(v), len(v), len(val))
        key += k.encode() + b'\0'
        val += v
    kpos = 20 + 16 * len(rows)
    vpos = kpos + len(key)
    return b'\0PSF' + struct.pack('<IIII', 0x101, kpos, vpos, len(rows)) + table + key + val

class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, filename, content):
        path = self.root / filename
        path.write_bytes(content)
        return path

    def test_sfo_read(self):
        m = read_sfo(self.write('PARAM.SFO', fake_sfo()))
        self.assertEqual(m['fields']['TITLE_ID'], 'NPUA80918')
        self.assertEqual(m['fields']['VERSION'], '01.00')

    def test_self_header(self):
        m = read_self(self.write('EBOOT.BIN', fake_self()))
        self.assertEqual(m['embedded_elf_offset'], 0x90)
        self.assertIn('PowerPC64', m['embedded_architecture'])
        self.assertFalse(m['encrypted_payload_readable'])

    def test_wrong_self_rejected(self):
        with self.assertRaises(PreflightError):
            read_self(self.write('bad.bin', b'\x7fELF' + bytes(100)))

    def test_sfo_bounds_validation(self):
        data = bytearray(fake_sfo())
        struct.pack_into('<I', data, 8, len(data) + 500)
        with self.assertRaises(PreflightError):
            read_sfo(self.write('broken.SFO', bytes(data)))

    def test_combined_metadata_only(self):
        out = inventory(self.write('EBOOT.BIN', fake_self()), self.write('PARAM.SFO', fake_sfo()))
        self.assertEqual(out['schema'], 'ascension-recomp/package-preflight-v1')
        self.assertEqual(out['param_sfo']['fields']['TITLE_ID'], 'NPUA80918')
        self.assertEqual(out['self']['elf_program_headers'], 3)

if __name__ == '__main__':
    unittest.main()
