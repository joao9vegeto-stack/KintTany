"""Signed ARM64 native stream ABI vs real C fallback; no IPA rebuild needed."""
import ast,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]/"scripts/repack_ktgl_source_dual_repair.py"
C_TEST=r"""
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
/* CALLBACKS_INSERT_HERE */
int main(void){
 unsigned char data[18340],out[20000];
 for(unsigned i=0;i<sizeof data;i++)data[i]=(unsigned char)(i&255);
 f2_reader_t a={0,0,data,48};
 assert(f2_skip(&a,4)==4);assert(f2_skip(&a,4)==4);
 assert(f2_skip(&a,50)==40);assert(f2_skip(&a,1)==0);assert(a.cur==48);
 f2_reader_t b={0,0,data,48};
 assert(f2_read(&b,out,0,20)==20);
 assert(f2_read(&b,out+20,0,20)==20);
 assert(f2_read(&b,out+40,0,20)==8);
 assert(!memcmp(data,out,48));assert(f2_read(&b,out,0,1)==0);
 f2_reader_t c={0,0,data,18340};
 assert(f2_read(&c,out,0,184)==184);
 assert(f2_skip(&c,16384)==16384);
 assert(f2_read(&c,out,0,4096)==1772);
 assert(c.cur==18340);assert(f2_read(&c,out,0,1)==0);
 puts("A64_BYTE_COUNT_ABI_AND_PARTIAL_READS_PASS");
}
"""
def actual_host_functions():
    parsed=ast.parse(SRC.read_text())
    expr=next(n.value for n in parsed.body if isinstance(n,ast.Assign)
       and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)
       and n.targets[0].id=="HOST_C")
    host=ast.literal_eval(expr)
    start=host.index("typedef struct {const void **vt;")
    end=host.index("static const void *f2_vt[5]")
    return host,host[start:end]
class ABI(unittest.TestCase):
 def test_signed_guest_virtual_contract_proven(self):
    # Actual signed IPA disassembly: run 45094304340 artifact 14782159778.
    # main+c095e0 cmp x20,x1 ; c095e8 ldr [vt+0x18]
    # main+c095f0 sub x8,x20,x0 ; c0961c cmp x20,x3
    # main+c09624 ldr [vt+0x20] ; c0962c sub x8,x20,x0.
    host,callbacks=actual_host_functions()
    self.assertEqual(callbacks.count("return consumed;"),2)
    self.assertNotIn("return r->cur;",callbacks)
    self.assertIn("f2_auth_g1t,48",host)
    self.assertIn("f2_auth_g1s,18340",host)
    self.assertIn("0x61210cu",host)
    self.assertIn("0x6e7b94u",host)
 def test_compile_host_code_and_execute_abi_against_g1t_g1s_sizes(self):
    compiler=shutil.which("clang") or shutil.which("gcc")
    self.assertIsNotNone(compiler,"C compiler required, not optional")
    _,funcs=actual_host_functions()
    with tempfile.TemporaryDirectory() as tmp:
       path=Path(tmp)/"abi.c";bin=Path(tmp)/"abi"
       path.write_text(C_TEST.replace("/* CALLBACKS_INSERT_HERE */",funcs))
       subprocess.run([compiler,"-std=c11","-O2","-Wall","-Wextra","-Werror",
                       str(path),"-o",str(bin)],check=True,capture_output=True,text=True)
       res=subprocess.run([str(bin)],check=True,capture_output=True,text=True)
       self.assertIn("A64_BYTE_COUNT_ABI_AND_PARTIAL_READS_PASS",res.stdout)
if __name__=="__main__":unittest.main()
