"""Mac-validated exact AArch64 KTGL capacity repack guard."""
import sys
import importlib.util
import unittest
from pathlib import Path
file=Path(__file__).resolve().parents[1]/"scripts/repack_ktgl_cap.py"
sys.path.insert(0,str(file.parent))
s=importlib.util.spec_from_file_location("fairy2_ktgl_repack",file)
m=importlib.util.module_from_spec(s)
sys.modules[s.name]=m
s.loader.exec_module(m)
class Test(unittest.TestCase):
 def test_source_mac_provenance(self):
  self.assertEqual(m.SOURCE_RUN,44983552364)
  self.assertEqual(m.PROOF_RUN,44986356916)
  self.assertEqual(m.RESERVED_BYTES,0x50000000)
  self.assertEqual(m.RESERVED_BYTES,m.CAP_UNITS*4)
  self.assertEqual(len(m.INSTRUCTIONS),2)
 def test_exact_arm64_movz(self):
  from audit_ktgl_cap import movz_x
  self.assertEqual(m.INSTRUCTIONS[0][2],movz_x(8,m.CAP_UNITS).hex())
  self.assertEqual(m.INSTRUCTIONS[1][2],movz_x(25,m.CAP_UNITS).hex())
 def test_unknown_guest_fails_closed(self):
  with self.assertRaisesRegex(RuntimeError,"wrong guest build opcode"):
   m.patch_two_caps(bytes(max(x[0] for x in m.INSTRUCTIONS)+64))
 def test_no_shader_host_recompile(self):
  txt=file.read_text()
  self.assertIn('base.make(source,output,report)',txt)
  self.assertIn('base.check_framework=check_framework',txt)
  self.assertIn('only eight bytes in two guest instructions may change',txt)
  for x in ('run("xcodebuild"','run("dmsh_build.py"','run("build_ipa_from_nsp.py"'):
   self.assertNotIn(x,txt)
