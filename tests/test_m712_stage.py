"""Synthetic M7.12 owner AOT secret verification, no game source in git."""
import base64
import gzip
import hashlib
import unittest
from tools import stage_m78_aot as s

def make_source(symbols):
    digest=bytes.fromhex(s.OWNER_ELF_SHA256)
    sha=b", ".join(f"0x{b:02x}".encode() for b in digest)
    prefix=b"static const unsigned char ar_source_sha256[32] = {"+sha+b"};\n"
    return (prefix + b"int ar_private_aot_install_sha256(void) {return 0;}\n" +
            b"\n".join(f"int {name}(void) {{return 0;}}".encode()
                       for name in symbols) + b"\n")

def encoded(src):
    return base64.b64encode(gzip.compress(src)).decode("ascii")

class M712SecretGate(unittest.TestCase):
    def test_accept_owner_elf_identity_and_60_distinct_entries(self):
        names=set(s.EXPECTED_SYMBOLS)|{s.M712_NEXT_PC}
        source=make_source(names)
        data,actual,sha=s.decode_owner_m712(encoded(source))
        self.assertEqual(data,source)
        self.assertEqual(actual,sorted(names))
        self.assertEqual(sha,hashlib.sha256(source).hexdigest())
    def test_fail_closed_wrong_elf_missing_next_or_bad_base64(self):
        names=set(s.EXPECTED_SYMBOLS)|{s.M712_NEXT_PC}
        data=make_source(names)
        bad=data.replace(b"0x4b",b"0x4c",1)
        with self.assertRaisesRegex(ValueError,"ELF SHA256 mismatched"):
            s.decode_owner_m712(encoded(bad))
        with self.assertRaisesRegex(ValueError,"required native game entries missing"):
            s.decode_owner_m712(encoded(make_source(s.EXPECTED_SYMBOLS)))
        with self.assertRaisesRegex(ValueError,"strict base64"):
            s.decode_owner_m712("@")
    def test_bounded_decompression(self):
        data=b"z"*(s.M712_MAX_SOURCE+1)
        with self.assertRaisesRegex(ValueError,"exceed bound"):
            s.decode_owner_m712(encoded(data))

if __name__=="__main__":
    unittest.main()
