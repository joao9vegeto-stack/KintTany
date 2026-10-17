"""M7.31 canonical XFX mtcrf/mtocrf to native C, strict CR masks."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_m23_cfg_lifter import run_c,BLR
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ppu_cfg_lifter import lift,Unsupported
def mt(rs=12,fxm=8,l=1,extra=0):
 return (31<<26)|(rs<<21)|(l<<20)|(fxm<<12)|(144<<1)|extra
class M731CR(unittest.TestCase):
 def test_exact_observed_mtocrf_cr4_word(self):
  self.assertEqual(mt(),0x7d908120)
  source,h=lift([mt(),BLR],0x52da5c)
  self.assertEqual(h['mtocrf'],1)
  self.assertIn('0x0000f000U',source)
  self.assertIn('c->gpr[12]',source)
  self.assertNotIn('ar_ppc_fallback_step',source)
 def test_mfcr_mtocrf_roundtrip_native(self):
  # Initial CR zero; r12 starts all ones, update CR4 then MFCR -> GPR13.
  mfcr=(31<<26)|(13<<21)|(19<<1)
  run_c([mt(rs=12,fxm=8,l=1),mfcr,BLR],regs={12:0xffffffffffffffff},
        checks=['rc==0','ctx.cr==0x0000f000U',
                'ctx.gpr[13]==0x0000f000ULL',
                'ctx.gpr[12]==UINT64_MAX'])
 def test_all_fields_mtcrf(self):
  _,h=lift([mt(rs=3,fxm=0xff,l=0),BLR],0x10000)
  self.assertEqual(h['mtcrf'],1)
  run_c([mt(rs=3,fxm=0xff,l=0),BLR],regs={3:0x12345678},
        checks=['rc==0','ctx.cr==0x12345678U',
                'ctx.gpr[3]==0x12345678ULL'])
 def test_sparse_fields_mask(self):
  src,h=lift([mt(rs=5,fxm=0x81,l=0),BLR],0x10000)
  self.assertEqual(h['mtcrf'],1)
  self.assertIn('0xf000000fU',src)
  run_c([mt(rs=5,fxm=0x81,l=0),BLR],regs={5:0x12345678},
        checks=['rc==0','ctx.cr==0x10000008U'])
 def test_reserved_and_multibit_one_field_rejected(self):
  for insn in (mt(fxm=0x81,l=1),mt(extra=0x800),
               mt(extra=1),mt(fxm=0,l=1)):
   with self.subTest(insn=f'{insn:08X}'):
    with self.assertRaises(Unsupported):lift([insn,BLR],0x10000)
 def test_compiled_aot_has_no_interpreter(self):
  src,h=lift([mt(rs=12,fxm=8,l=1),BLR],0x52da5c)
  self.assertEqual(h.get('mtocrf'),1)
  self.assertNotIn('ar_ppc_fallback_step',src)
if __name__=="__main__":unittest.main()
