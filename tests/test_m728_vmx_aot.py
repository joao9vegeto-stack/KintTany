"""M7.28 VMX -> C -> native host machine code (no private game bytes)."""
from __future__ import annotations
import pathlib, shutil, subprocess, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from ppu_cfg_lifter import lift, Unsupported
BLR=0x4e800020

def vx(vd,va,vb,xo):return (4<<26)|(vd<<21)|(va<<16)|(vb<<11)|xo
def x(vd,ra,rb,xo):return (31<<26)|(vd<<21)|(ra<<16)|(rb<<11)|(xo<<1)
def run_native(words,init="",checks=()):
    cc=shutil.which("clang") or shutil.which("cc")
    if not cc:raise unittest.SkipTest("no C compiler")
    code,hist=lift(words,0x10000,"native_ppu_vmx")
    chk="\n".join(f"if(!({c})) return {30+i};" for i,c in enumerate(checks))
    source=code+f"""
int main(void){{
 if(ar_bridge_init(0x3000)!=AR_OK)return 2;
 ppu_ctx ctx={{0}};ctx.lr=0x1100ULL;
 {init}
 int rc=native_ppu_vmx(&ctx);
 {chk}
 ar_bridge_shutdown();
 return 0;
}}
"""
    with tempfile.TemporaryDirectory() as td:
        c=pathlib.Path(td)/"code.c";a=pathlib.Path(td)/"app"
        c.write_text(source,encoding="utf-8")
        args=[cc,"-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-label","-Wno-unused-function",
              "-O2","-fsanitize=undefined","-I",str(ROOT/"tests/fixtures"),
              "-I",str(ROOT/"runtime"),str(c),
              str(ROOT/"runtime/ppu_bridge.c"),"-o",str(a)]
        out=subprocess.run(args,capture_output=True,text=True,timeout=35)
        if out.returncode:raise AssertionError(out.stderr[:2500])
        out=subprocess.run([str(a)],capture_output=True,text=True,timeout=10)
        if out.returncode:raise AssertionError(f"exit={out.returncode} {out.stderr[:1300]}")
    return code,hist

class TestM728NativeVMX(unittest.TestCase):
    def test_signed_splat_native(self):
        source,h=run_native([vx(5,31,0,908),BLR],checks=[
            "rc==0","ctx.cia==0x1100ULL",
            "ctx.vr[5].d[0]==0xffffffffffffffffULL",
            "ctx.vr[5].d[1]==0xffffffffffffffffULL"])
        self.assertEqual(h.get("vspltisw"),1)
        self.assertIn("ar_vmx_splat_imm",source)
        self.assertNotIn("ar_ppc_fallback_step",source)
    def test_vector_splat_alias(self):
        run_native([vx(3,31,0,908),vx(3,2,3,652),BLR],
            checks=["rc==0","ctx.vr[3].d[0]==UINT64_MAX",
                    "ctx.vr[3].d[1]==UINT64_MAX"])
    def test_16byte_aligned_load_store(self):
        run_native([x(5,0,8,103),x(5,0,9,231),BLR],
            init="""uint8_t arr[16];for(unsigned i=0;i<16;i++)arr[i]=(uint8_t)(0x80+i);
                    if(ar_vm_load(0x1800,arr,16)!=AR_OK)return 3;
                    ctx.gpr[8]=0x180fu;ctx.gpr[9]=0x182eu;""",
            checks=["rc==0","ar_read8(0x1820)==0x80",
                    "ar_read8(0x182f)==0x8f",
                    "ctx.vr[5].d[0]==0x8081828384858687ULL"])
    def test_cell_lvlx_and_vspltw_native(self):
        source,h=run_native([x(3,4,5,519),vx(6,2,3,652),x(6,0,9,231),BLR],
            init="""uint8_t a[16];for(unsigned i=0;i<16;i++)a[i]=(uint8_t)i;
                    if(ar_vm_load(0x1800,a,16)!=AR_OK)return 3;
                    ctx.gpr[4]=0x1803;ctx.gpr[5]=0;ctx.gpr[9]=0x1820;""",
            checks=["rc==0","ar_read32(0x1820)==0x0b0c0d0eU",
                    "ar_read32(0x182c)==0x0b0c0d0eU",
                    "ctx.vr[3].d[1]==0x0b0c0d0e0f000000ULL"])
        self.assertEqual(h["vmx_load"],1)
        self.assertEqual(h["vspltw"],1)
        self.assertEqual(h["vmx_store"],1)
        self.assertNotIn("ar_ppc_fallback_step",source)
    def test_strict_isa_invalid_form(self):
        for words in ([vx(5,0,1,908),BLR],
                      [vx(5,4,3,652),BLR],
                      [x(2,0,3,519)|1,BLR],
                      [vx(5,0,0,0x444),BLR]):
            with self.subTest(word=f"{words[0]:08x}"):
                with self.assertRaises(Unsupported):lift(words,0x10000)
if __name__=="__main__":unittest.main()
