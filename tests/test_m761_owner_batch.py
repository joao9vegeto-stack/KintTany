"""M7.61 actual owner batch: non-synthetic PPC bytes, strict full-span lifting."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from generate_m761_owner_batch import ELF_SHA,STOP_PC,spans,emit,authenticate
class M761(unittest.TestCase):
 def test_verified_structure_and_reproducible_discovery(self):
  rows=spans()
  self.assertEqual(ELF_SHA,"4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5")
  self.assertEqual(len(rows),26)
  self.assertEqual(sum(len(w) for _,w in rows),739)
  self.assertEqual(len({p for p,_ in rows}),26)
  self.assertEqual(dict(rows)[STOP_PC][0],0xf821ff91)
  self.assertEqual(dict(rows)[STOP_PC][-1],0x4e800020)
 def test_translates_beyond_single_block(self):
  source,report=emit()
  self.assertGreaterEqual(report["generated_native_entries"],2)
  self.assertGreaterEqual(report["generated_native_ppc_words"],18)
  self.assertIn("ar_m761_native_003e16e0",source)
  self.assertIn("ar_m761_register_owner",source)
  self.assertIn("ar_m712_exec_window",source)
  self.assertIn("ar_last_error()!=AR_OK",source)
  self.assertIn("ar_guest_call(c,0x3c5218ULL)",source)
  self.assertIn("ar_register(q->pc,q->fn)",source)
  self.assertNotIn("ar_ppc_fallback",source)
  self.assertEqual(report["executed_on_iphone"],"NÃO MEDIDO")
  self.assertLessEqual(report["generated_native_entries"],26)
 def test_refuses_unrelated_or_missing_elf(self):
  with self.assertRaises((ValueError,OSError)):
   authenticate(ROOT/"tests"/"fixtures"/"ppu_context.h")
 def test_production_wiring(self):
  b=(ROOT/"tools"/"build_ios_probe_ipa.sh").read_text()
  bridge=(ROOT/"ios"/"ARLivePPUBridge.c").read_text()
  wf=(ROOT/".github"/"workflows"/"ascension-recomp-m0.yml").read_text()
  self.assertIn("ppu_m761_generated.o",b)
  self.assertIn("ar_m761_register_owner(d,len)",bridge)
  self.assertIn("m761-native-arm64.o",wf)
  self.assertNotIn("runtime/ppu_m761_generated.c\n",wf.split("path:",1)[-1])
if __name__=="__main__":unittest.main()
