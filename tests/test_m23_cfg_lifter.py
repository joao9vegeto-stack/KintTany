"""Synthetic PowerPC64 branch/rotation tests, compiled and EXECUTED on host."""
from __future__ import annotations
import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ppu_cfg_lifter import Unsupported, lift, mask64
BLR=0x4e800020
def li(rd,imm):return (14<<26)|(rd<<21)|(imm&0xffff)
def addi(rd,ra,imm):return (14<<26)|(rd<<21)|(ra<<16)|(imm&0xffff)
def cmpwi(ra,imm):return (11<<26)|(ra<<16)|(imm&0xffff)
def bc(bo,bi,d):return (16<<26)|(bo<<21)|(bi<<16)|(d&0xfffc)
def b(d):return (18<<26)|(d&0x3fffffc)
STUBS=r'''
u64 ar_read64(u64 a) {(void)a;return 0;}
u32 ar_read32(u64 a) {(void)a;return 0;}
uint16_t ar_read16(u64 a) {(void)a;return 0;}
uint8_t ar_read8(u64 a) {(void)a;return 0;}
void ar_write64(u64 a,u64 v) {(void)a;(void)v;}
void ar_write32(u64 a,u32 v) {(void)a;(void)v;}
void ar_write16(u64 a,uint16_t v) {(void)a;(void)v;}
void ar_write8(u64 a,uint8_t v) {(void)a;(void)v;}
int ar_guest_call(ppu_ctx *c,u64 t){(void)c;(void)t;return 0;}
'''
def run_c(words,regs=None,ctr=0,lr=0x1234,checks=None):
    compiler=shutil.which('cc') or shutil.which('clang')
    if not compiler:raise unittest.SkipTest('C compiler unavailable')
    src,_=lift(words,0x10000,'native_probe')
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)
        init='\n'.join(f'ctx.gpr[{idx}]={val}ULL;' for idx,val in (regs or {}).items())
        asserts='\n'.join('if(!('+stmt+f')) return {i+10};' for i,stmt in enumerate(checks or []))
        app=src+STUBS+f'''
int main(void) {{
    ppu_ctx ctx={{0}}; ctx.lr={lr}ULL; ctx.ctr={ctr}ULL;
    {init}
    int rc=native_probe(&ctx);
    {asserts}
    return 0;
}}
'''
        (p/'probe.c').write_text(app)
        cp=subprocess.run([compiler,'-std=c11','-O2','-I',str(Path(__file__).resolve().parent/'fixtures'),str(p/'probe.c'),'-o',str(p/'probe')],capture_output=True,text=True,timeout=20)
        if cp.returncode:raise AssertionError('native compile failed: '+cp.stderr[:1300])
        result=subprocess.run([str(p/'probe')],capture_output=True,text=True,timeout=10)
        if result.returncode:raise AssertionError(f'native test failed exit={result.returncode} {result.stderr}')
class M23BranchTests(unittest.TestCase):
    def test_beq_taken(self):
        run_c([li(3,0),cmpwi(3,0),bc(12,2,12),li(3,42),b(8),li(3,7),BLR],
              checks=['rc==0','ctx.gpr[3]==7','ctx.cia==0x1234'])
    def test_beq_not_taken(self):
        run_c([li(3,1),cmpwi(3,0),bc(12,2,12),li(3,42),b(8),li(3,7),BLR],
              checks=['rc==0','ctx.gpr[3]==42'])
    def test_ctr_decrement_loop(self):
        run_c([li(3,0),addi(3,3,1),bc(16,0,-4),BLR],ctr=3,
              checks=['rc==0','ctx.gpr[3]==3','ctx.ctr==0'])
    def test_conditional_bclr_taken_returns_to_caller(self):
        beqlr=(19<<26)|(12<<21)|(2<<16)|(16<<1)
        run_c([cmpwi(3,5),beqlr,li(3,99),BLR],regs={3:5},
              checks=['rc==0','ctx.gpr[3]==5','ctx.cia==0x1234'])

    def test_conditional_bclr_not_taken_falls_through(self):
        beqlr=(19<<26)|(12<<21)|(2<<16)|(16<<1)
        run_c([cmpwi(3,5),beqlr,li(3,99),BLR],regs={3:4},
              checks=['rc==0','ctx.gpr[3]==99','ctx.cia==0x1234'])

    def test_bctr_external_tail(self):
        run_c([0x4e800420],ctr=0xbeef,checks=['rc==1','ctx.cia==0xbeef'])
    def test_external_b_tail(self):
        run_c([b(12)],checks=['rc==1','ctx.cia==0x1000c'])
    def test_rldicl_clear_low32(self):
        run_c([0x787e0020,BLR],regs={3:0xffffffffdeadbeef},
              checks=['rc==0','ctx.gpr[30]==0xdeadbeefULL'])
    def test_rldicr_shift_left(self):
        run_c([0x7bc33e24,BLR],regs={30:1},checks=['rc==0','ctx.gpr[3]==128ULL'])
    def test_rldimi_merge(self):
        mb=mask64(5,5)
        prev=0x5555555555555555; value=0xaabbccdd11223344
        rot=((value<<58)|(value>>(64-58)))&((1<<64)-1)
        expected=(prev&(~mb&((1<<64)-1)))|(rot&mb)
        run_c([0x78a7d14e,BLR],regs={5:value,7:prev},
              checks=['rc==0',f'ctx.gpr[7]==0x{expected:x}ULL'])
    def test_addc_xer_ca(self):
        word=(31<<26)|(3<<21)|(4<<16)|(5<<11)|(10<<1)
        run_c([word,BLR],regs={4:(1<<64)-1,5:1},
              checks=['rc==0','ctx.gpr[3]==0','(ctx.xer & 0x20000000U)!=0'])
    def test_unsupported_fails_closed(self):
        with self.assertRaises(Unsupported):lift([0xffffffff,BLR],0x10000)
    def test_incomplete_function_rejected(self):
        with self.assertRaisesRegex(Unsupported,'terminator'):lift([li(3,42)],0x10000)
    def test_vector_opcode_requires_full_lifter(self):
        with self.assertRaisesRegex(Unsupported,'opcode4'):lift([0x10000000,BLR],0x10000)
if __name__=='__main__':unittest.main()
