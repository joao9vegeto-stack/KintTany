"""Compile the actual original-data KTGL reader recovery with 4 data sizes.

The real game resources are not distributed in this test: C compressed input
comes from zlib in-memory, is wrapped in the original u16+8 mode4 record,
then the production function must restore the reader's actual cache/cursors.
Corrupted Adler32 and invalid state must not touch the reader.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/"scripts/ktgl_zlib_fallback_host.h"
DIRECT=ROOT/"scripts/ktgl_direct_reader_recovery_host.h"
SCRIPT=ROOT/"scripts/repack_mode4_direct.py"
C_TEST=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <zlib.h>
#include <dlfcn.h>
%s
%s
static void run_case(unsigned size, unsigned request) {
    unsigned char plain[16384], packed[30000], raw[30016];
    unsigned char reader[0x4050], dest[16384], before[0x4050];
    assert(request>0 && request<=size && size<=16384);
    for (unsigned i=0; i<size; ++i)
        plain[i]=(unsigned char)((i*61u+23u)&255u);
    uLongf compressed_length=sizeof packed;
    assert(compress2(packed,&compressed_length,plain,size,Z_BEST_SPEED)==Z_OK);
    assert(compressed_length<65520u);
    uint16_t header=(uint16_t)compressed_length;
    memcpy(raw,&header,2);
    memcpy(raw+2,"KTGLRDB!",8);
    memcpy(raw+10,packed,compressed_length);
    size_t raw_n=10+compressed_length;
    memset(reader,0,sizeof reader);
    memset(dest,0x5a,sizeof dest);
    uint64_t pointer=(uint64_t)(uintptr_t)raw, limit=raw_n;
    memcpy(reader+8,&pointer,8);
    memcpy(reader+0x18,&limit,8);
    struct f2_direct_snapshot s={0};
    s.reader=(uint64_t)(uintptr_t)reader;
    s.destination=(uint64_t)(uintptr_t)dest;
    s.requested=request;
    s.raw=pointer;
    s.compressed_pos=0;
    s.compressed_end=limit;
    assert(f2_direct_recover_original_block(&s));
    assert(!memcmp(dest,plain,request));
    assert(dest[request]==0x5a || request==sizeof dest);
    assert(!memcmp(reader+0x30,plain,size));
    uint64_t cursor=0, end=0, compressed_cursor=0, pointer_after=0;
    memcpy(&cursor,reader+0x20,8); memcpy(&end,reader+0x28,8);
    memcpy(&compressed_cursor,reader+0x10,8);
    memcpy(&pointer_after,reader+0x8,8);
    assert(cursor==request && end==size);
    assert(compressed_cursor==raw_n && pointer_after==pointer);

    /* Any invalid source must be fail-closed, with zero guest mutation. */
    memset(reader,0,sizeof reader);
    memcpy(reader+8,&pointer,8);memcpy(reader+0x18,&limit,8);
    memset(dest,0x5a,sizeof dest);
    memcpy(before,reader,sizeof reader);
    raw[raw_n-1]^=0x10; // guaranteed bad Adler32
    assert(!f2_direct_recover_original_block(&s));
    assert(!memcmp(reader,before,sizeof reader) && dest[0]==0x5a);
    raw[raw_n-1]^=0x10;
    s.decoded_pos=1; s.decoded_end=1;
    assert(!f2_direct_recover_original_block(&s)); // non-first-block disallowed
    s.decoded_pos=0;s.decoded_end=0;
    s.compressed_end=raw_n-1; // truncation
    assert(!f2_direct_recover_original_block(&s));
    s.compressed_end=raw_n;
    s.requested=size+1;
    assert(!f2_direct_recover_original_block(&s));
}
int main(void) {
    f2_inflate_init=inflateInit2_;
    f2_inflate_run=inflate;
    f2_inflate_end=inflateEnd;
    run_case(48,28);
    run_case(184,184);
    run_case(1956,184);
    run_case(16384,184);
    puts("KTGL ORIGINAL MODE4 DIRECT READ STATE/ADLER32 PASS");
    return 0;
}
'''

class DirectReader(unittest.TestCase):
    def test_static_source_and_only_failed_read_contract(self):
        h=DIRECT.read_text()
        s=SCRIPT.read_text()
        for key in ("FAIRY2_KTGL_DIRECT_MODE4_SOURCE_RECOVERY",
                    "main+0x2a64b50", "original==0", "s->decoded_pos != 0",
                    "f2_zlib_original_chunk(f2_direct_verified_output, F2_ZLIB_MAX_OUT",
                    "f2_direct_reader_pop(", "compressed_end - s->compressed_pos"):
            if key=="main+0x2a64b50":
                self.assertIn(key,s)
            else:
                self.assertIn(key,h)
        self.assertIn("only_when_read_returns_zero",s)
        self.assertNotIn("fairy2_known_g1t",h)
        self.assertNotIn("GT1G05000",h)
        self.assertIn("0xc11b80",s)
        self.assertIn("0xc11f9c",s)

    def test_critical_guest_opcodes_match_private_original_nso(self):
        source=SCRIPT.read_text()
        self.assertIn('0xc11b80: bytes.fromhex("08a440a9")',source)
        self.assertIn('0xc11f9c: bytes.fromhex("e00313aa")',source)
        self.assertIn("main_sections",source)
        self.assertIn("pieces[\"w\"][\"data\"]==out[\"w\"][\"data\"]",source)

    def test_compiled_real_fallback_retains_cache_and_rejects_bad_adler32(self):
        pre=NATIVE.read_text().split("static int f2_zlib_fail_path_trap(",1)[0]
        direct=DIRECT.read_text().split("/* DARWIN_SIGNAL_ONLY",1)[0]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            src=root/"direct.c";exe=root/"direct"
            src.write_text(C_TEST%(pre,direct))
            proc=subprocess.run(["cc","-O2","-Wall","-Wextra",
              "-Wno-unused-function",str(src),"-ldl","-lz","-o",str(exe)],
              text=True,capture_output=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            run=subprocess.run([str(exe)],text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("STATE/ADLER32 PASS",run.stdout)

if __name__=="__main__":
    unittest.main()
