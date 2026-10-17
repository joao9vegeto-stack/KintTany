"""M7.24 NEG/NEGO ISA correctness for static PPC64->native C lifting.

All words and values are synthetic, never extracted from a commercial game.
The independently specified oracle tests XER OV/SO and CR0 Rc behavior.
"""
from __future__ import annotations
import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))
from ppu_cfg_lifter import lift, Unsupported
from test_m23_cfg_lifter import STUBS, BLR

def neg(rt=3,ra=4,oe=False,rc=False,rb=0):
    return (31<<26)|(rt<<21)|(ra<<16)|(rb<<11)|((104+(512 if oe else 0))<<1)|int(rc)

def verify(words,regs=None,xer=0,cr=0,checks=()):
    compiler=shutil.which("clang") or shutil.which("cc")
    if not compiler:raise unittest.SkipTest("C compiler unavailable")
    source,_=lift(words,0x10000,"test_native_neg")
    regs=regs or {}
    initial="\n".join(f"ctx.gpr[{i}]=0x{v:x}ULL;" for i,v in regs.items())
    assertions="\n".join(f"if(!({v})) return {10+i};" for i,v in enumerate(checks))
    app=source+STUBS+f"""
int main(void){{
    ppu_ctx ctx={{0}};ctx.lr=0x1234ULL;ctx.xer=0x{xer:x}U;ctx.cr=0x{cr:x}U;
    {initial}
    int rc=test_native_neg(&ctx);
    {assertions}
    return 0;
}}
"""
    with tempfile.TemporaryDirectory() as td:
        c=Path(td)/"test.c";exe=Path(td)/"test"
        c.write_text(app,encoding="utf8")
        flags=[compiler,"-std=c11","-O2","-fsanitize=undefined",
               "-I",str(ROOT/"tests/fixtures"),str(c),"-o",str(exe)]
        compiled=subprocess.run(flags,capture_output=True,text=True,timeout=25)
        if compiled.returncode:raise AssertionError("AOT compile failed: "+compiled.stderr[:1400])
        ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
        if ran.returncode:raise AssertionError(f"AOT result failed: exit {ran.returncode}: "+ran.stderr[:1400])

class M724Neg(unittest.TestCase):
    def test_neg_positive_modular_no_overflow_writes(self):
        verify([neg(),BLR],{4:7},xer=0xe0000000,cr=0x12345678,
               checks=("rc==0","ctx.gpr[3]==0xfffffffffffffff9ULL",
                       "ctx.xer==0xe0000000U","ctx.cr==0x12345678U"))
    def test_neg_zero_records_eq_and_so(self):
        verify([neg(rc=True),BLR],{4:0},xer=0x80000000,cr=0x12345678,
               checks=("rc==0","ctx.gpr[3]==0",
                       "(ctx.cr&0xf0000000U)==0x30000000U",
                       "(ctx.cr&0x0fffffffU)==0x02345678U"))
    def test_neg_min_signed_64_without_oe_has_no_undefined_behavior(self):
        verify([neg(),BLR],{4:0x8000000000000000},xer=0x20000000,
               checks=("rc==0","ctx.gpr[3]==0x8000000000000000ULL",
                       "ctx.xer==0x20000000U"))
    def test_nego_min_records_overflow_sticky_so_and_lt(self):
        verify([neg(oe=True,rc=True),BLR],{4:0x8000000000000000},
               xer=0x20000000,cr=0x000000ab,
               checks=("rc==0","ctx.gpr[3]==0x8000000000000000ULL",
                       "ctx.xer==0xe0000000U",
                       "ctx.cr==0x900000abU"))
    def test_nego_nonoverflow_clears_ov_preserves_sticky_so_and_ca(self):
        verify([neg(oe=True,rc=True),BLR],{4:0xfffffffffffffffd},
               xer=0xe0000000,cr=0x000000ab,
               checks=("rc==0","ctx.gpr[3]==3ULL",
                       "ctx.xer==0xa0000000U",
                       "ctx.cr==0x500000abU"))
    def test_aliased_register_and_following_64_bit_rotate(self):
        # Synthetic rotate: rldicl r5,r5,0,32 (not a game opcode sequence).
        md=(30<<26)|(5<<21)|(5<<16)|(32&32)
        verify([neg(5,5),md,BLR],{5:1},
               checks=("rc==0","ctx.gpr[5]==0xffffffffULL","ctx.cia==0x1234ULL"))
    def test_illegal_reserved_rb_rejected_without_placeholder_nop(self):
        with self.assertRaisesRegex(Unsupported,"reserved RB"):
            lift([neg(rb=3),BLR],0x10000)
        code,hist=lift([neg(oe=True,rc=True),BLR],0x10000)
        self.assertEqual(hist.get("nego"),1)
        self.assertIn("0ULL-neg_src_",code)
        self.assertNotIn("ar_ppc_fallback_step",code)

if __name__=="__main__": unittest.main()
