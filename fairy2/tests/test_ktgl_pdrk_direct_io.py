"""C regression against exact failed PDRK headers and working upstream shape."""
import pathlib,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
H=ROOT/"scripts/ktgl_pdrk_no_preload.h"
C=r"""
#include <assert.h>
#include <stdio.h>
#include "ktgl_pdrk_no_preload.h"
int main(void) {
    const unsigned char h[16]={'P','D','R','K','0','0','0','0',0x10,0,0,0,0x79,0xe1,0x2f,0};
    const unsigned char h2[16]={'P','D','R','K','0','0','0','0',0x10,0,0,0,0x48,0xf6,0x2f,0};
    unsigned char original[256],expected[256],out[256];
    for(unsigned i=0;i<sizeof original;i++)original[i]=(unsigned char)i;
    memcpy(original,h,16);memcpy(expected,original,sizeof original);
    memset(expected+12,0,4);
    assert(f2_pdrk_preload_extent(h,0xff35820)==0x2fe179);
    assert(f2_pdrk_preload_extent(h2,0x8f68bbd0)==0x2ff648);
    assert(f2_pdrk_preload_extent(expected,0xff35820)==0);
    /* Exhaustive overlapping read ranges, including one-byte reads and
       full-file reads. Only the four extension bytes may change. */
    for(unsigned off=0;off<sizeof original;off++){
      for(unsigned n=0;n<=sizeof original-off;n++){
        memset(out,0xcd,sizeof out);memcpy(out,original+off,n);
        size_t got=f2_pdrk_hide_preload(h,0xff35820,off,out,n);
        assert(got<=4);
        assert(!memcmp(out,expected+off,n));
        for(unsigned j=n;j<sizeof out;j++)assert(out[j]==0xcd);
      }
    }
    memcpy(out,original,sizeof out);
    assert(f2_pdrk_hide_preload(h,0x200,0,out,sizeof out)==0);
    assert(!memcmp(out,original,sizeof out));
    unsigned char bad[16];memcpy(bad,h,16);bad[0]='I';
    assert(f2_pdrk_hide_preload(bad,0xff35820,0,out,sizeof out)==0);
    bad[0]='P';bad[8]=0x20;
    assert(f2_pdrk_hide_preload(bad,0xff35820,0,out,sizeof out)==0);
    assert(f2_pdrk_hide_preload(expected,0xff35820,0,out,sizeof out)==0);
    assert(f2_pdrk_hide_preload(h,0xff35820,UINT64_MAX,out,16)==0);
    puts("PDRK_HEADER_REFERENCE_PARITY_ALL_READ_SLICES_PASS");
    return 0;
}
"""
class DirectIO(unittest.TestCase):
 def test_c_header_all_read_slices(self):
    compiler=shutil.which("clang") or shutil.which("gcc")
    self.assertIsNotNone(compiler)
    with tempfile.TemporaryDirectory() as tmp:
       p=pathlib.Path(tmp)/"test.c";b=pathlib.Path(tmp)/"test"
       p.write_text(C)
       subprocess.run([compiler,"-std=c11","-O2","-Wall","-Wextra","-Werror","-I",str(H.parent),str(p),"-o",str(b)],check=True)
       res=subprocess.run([str(b)],capture_output=True,text=True,check=True)
       self.assertIn("PDRK_HEADER_REFERENCE_PARITY_ALL_READ_SLICES_PASS",res.stdout)
 def test_no_synthetic_reader(self):
    s=(ROOT/"scripts/repack_ktgl_pdrk_direct_io.py").read_text()
    self.assertIn("no_per_resource_fallback",s)
    self.assertIn("no_guest_parser_traps",s)
    self.assertIn("0xc107d8:",s)
    self.assertIn("0xc11f54:",s)
    self.assertIn("coherent.make",s)
    self.assertNotIn("SOURCE_REPAIR_G1T",s)
    self.assertNotIn("write(trace.BREAK)",s)
if __name__=="__main__":unittest.main()
