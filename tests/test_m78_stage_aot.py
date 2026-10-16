"""Only synthetic sources used to test M7.8 secret's strict decoder."""
import base64
import gzip
import hashlib
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import stage_m78_aot as m


class TestM78Stage(unittest.TestCase):
    def test_pinned_owner_digest_and_symbols(self):
        src=(b"ar_private_aot_install_sha256 " +
             b" ".join(n.encode("ascii") for n in m.EXPECTED_SYMBOLS))
        text=base64.b64encode(gzip.compress(src)).decode()
        old=m.EXPECTED_SHA256
        try:
            m.EXPECTED_SHA256=hashlib.sha256(src).hexdigest()
            self.assertEqual(m.decode_verified(text),src)
            with self.assertRaisesRegex(ValueError,"strict base64"):
                m.decode_verified("@")
            with self.assertRaisesRegex(ValueError,"absent"):
                m.decode_verified("")
            with self.assertRaisesRegex(ValueError,"SHA256"):
                m.decode_verified(base64.b64encode(gzip.compress(src+b"!")).decode())
            with self.assertRaisesRegex(ValueError,"required entry"):
                x=src.replace(m.EXPECTED_SYMBOLS[0].encode(),b"no_entry")
                m.EXPECTED_SHA256=hashlib.sha256(x).hexdigest()
                m.decode_verified(base64.b64encode(gzip.compress(x)).decode())
        finally:
            m.EXPECTED_SHA256=old

    def test_decompression_limit(self):
        giant=b"ar_private_aot_install_sha256"+b"z"*256001
        encoded=base64.b64encode(gzip.compress(giant)).decode()
        with self.assertRaisesRegex(ValueError,"exceed bound"):
            m.decode_verified(encoded)
