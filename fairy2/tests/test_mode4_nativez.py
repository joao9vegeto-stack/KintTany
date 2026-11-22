"""Reference-bound KTGL mode4 fallback: compiled C RFC1950 data integrity tests.

No game resources; synthetic zlib compressed data with the original stored-byte
layout [8-byte KTGL prefix][RFC1950 + Adler32]. Both original and damaged
streams are tested. Native fallback is only available after guest failure.
"""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "scripts" / "ktgl_zlib_fallback_host.h"
PATCHER = ROOT / "scripts" / "repack_mode4_nativez.py"
fake = types.ModuleType("repack_full_resource_va")
fake.hook = types.SimpleNamespace(ENGINE_PIN="b526a50b85e4cfa3142c111e1ad491d9fd11f0eb")
fake.patch_main = lambda *args:None
fake.verify_main = lambda *args:None
fake.require = lambda b,s:None if b else (_ for _ in ()).throw(RuntimeError(s))
sys.modules["repack_full_resource_va"] = fake
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("fairy_native_mode4", PATCHER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

TEST_C = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <zlib.h>
#include <dlfcn.h>
#include <stdint.h>
/* The host-only fault interception uses Darwin's ucontext, so compile the
 * exact portable codec from our source header (before the hook). */
%s
int main(void) {
  f2_inflate_init = inflateInit2_;
  f2_inflate_run = inflate;
  f2_inflate_end = inflateEnd;
  unsigned char plain[16384], compressed[20000], framed[20008], dst[16384];
  for (unsigned i = 0; i < sizeof plain; ++i)
    plain[i] = (unsigned char)((i * 23u + 17u) & 255u);
  uLongf length = sizeof compressed;
  assert(compress2(compressed, &length, plain, sizeof plain, Z_BEST_SPEED) == Z_OK);
  assert(length + 8u <= sizeof framed);
  memcpy(framed, "KTGLRDB!", 8); memcpy(framed + 8, compressed, length);
  uint64_t written = 0;
  assert(f2_zlib_original_chunk(dst, sizeof dst, &written, framed, length + 8));
  assert(written == sizeof plain && !memcmp(plain, dst, written));
  /* Integrity and size gates must NOT produce synthetic data. */
  framed[length + 7] ^= 0xff;
  assert(!f2_zlib_original_chunk(dst, sizeof dst, &written, framed, length + 8));
  framed[length + 7] ^= 0xff;
  assert(!f2_zlib_original_chunk(dst, sizeof dst, &written, framed, length + 7));
  framed[8] = 0;
  assert(!f2_zlib_original_chunk(dst, sizeof dst, &written, framed, length + 8));
  framed[8] = compressed[0];
  assert(!f2_zlib_original_chunk(dst, 0, &written, framed, length + 8));
  assert(!f2_zlib_original_chunk(dst, 16385, &written, framed, length + 8));
  assert(!f2_zlib_original_chunk(dst, sizeof dst, &written, framed, 65536));
  puts("FAIRY2 GENERIC RFC1950 FALLBACK PASS: source intact, corruption rejected");
  return 0;
}
'''

class NativeMode4(unittest.TestCase):
    def test_original_native_only_and_failure_only(self):
        h = HOST.read_text()
        self.assertIn("FAIRY2_KTGL_MODE4_NATIVE_FALLBACK", h)
        self.assertIn("if (off == 0xc0ef8cULL)", h)
        self.assertIn("off != 0xc0f0d4ULL", h)
        self.assertIn("f2_zlib_tls.sp == uc->uc_mcontext->__ss.__sp", h)
        self.assertIn("status == Z_STREAM_END", h)
        self.assertIn("stream.avail_in == 0", h)
        self.assertIn("stream.total_in == stored - 8", h)
        self.assertIn("f2_is_zlib_header(source + 8)", h)
        self.assertNotIn("fb9ebd24", h.lower())
        self.assertNotIn("ac9ed13e", h.lower())
        self.assertNotIn("fairy2_known_g1t", h.lower())
    def test_original_guest_exact_opcode_guard(self):
        self.assertEqual(m.SITES, {
            0xc0ef8c: bytes.fromhex("e9e30191"),
            0xc0f0d4: bytes.fromhex("e0031f2a")})
        self.assertEqual(m.BRK, bytes.fromhex("40403ed4"))
    def test_no_native_retry_after_short_header(self):
        s = PATCHER.read_text()
        self.assertNotIn("bounded_retry_source", s)
        self.assertNotIn("fairy2_known_g1t", s)
        self.assertNotIn("FAIRY2_G1T_RECOVERY", s)
        self.assertIn("guest_parser_skipped", s)
        self.assertIn("original-mode4-zlib-report.json", s)
    def test_live_compile_and_data_integrity(self):
        code = HOST.read_text().split("static int f2_zlib_fail_path_trap(",1)[0]
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "codec_test.c"
            exe = Path(d) / "codec_test"
            src.write_text(TEST_C % code)
            build = subprocess.run(["cc", "-O2", "-Wall", "-Wextra",
                       "-Wno-unused-function", str(src), "-ldl", "-lz",
                       "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout+"\n"+build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout+"\n"+run.stderr)
            self.assertIn("CORRUPTION", run.stdout.upper().replace("corruption rejected","CORRUPTION REJECTED"))

if __name__ == "__main__":
    unittest.main()
