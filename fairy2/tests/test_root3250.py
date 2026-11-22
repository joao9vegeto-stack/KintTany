"""Fail-closed regression checks for the real A19 Pro root-region overrun."""
import sys,importlib.util,hashlib,unittest
from pathlib import Path
f=Path(__file__).resolve().parents[1]/"scripts"/"repack_root3250.py"
sys.path.insert(0,str(f.parent))
s=importlib.util.spec_from_file_location("fairy2_root_3250",f)
m=importlib.util.module_from_spec(s)
sys.modules[s.name]=m
s.loader.exec_module(m)
# Exact 64-byte AArch64 source snapshots after all previous fixes.
ORIGINAL_WINDOWS={
 0x5f1b9c:"e80080d2e800a0f2ff4300b9f78b0032a800c0f2ff3f00f90900b8d2ffff06a9ffff05a9e82703a9ffff04a98002029121008052e2031f2a9176739448ab47f9",
 0x1d700bc:"09815539490100372900805209811539287500b0082115910900b8d21f2500a9497300d029e11991090900f9c0035fd6fd7bbda9f50b00f9f44f02a9fd030091",
 0x225de0c:"0040009102488052e1031f2a68c70194e80080d2e800a0f20900b8d2a800c0f2682600a9a80080d20a5080d20a3cc0f22800c0f26a2a00f96a3a00f954008052",
 0x2295a44:"00000000ff8301d1fd7b04a9f32b00f9fd030191084b00d00900b8d2085d46f9134b00d00100b8d2090100f9736246f9e00313aa1ce60094094b00d0680240f9",
 0x2295a50:"f32b00f9fd030191084b00d00900b8d2085d46f9134b00d00100b8d2090100f9736246f9e00313aa1ce60094094b00d0680240f9e0230091296546f9280100f9",
}
class RootRegionTest(unittest.TestCase):
 def make_fixture(self):
  b=bytearray(max(ORIGINAL_WINDOWS)+64)
  for off,window in ORIGINAL_WINDOWS.items(): b[off-24:off+40]=bytes.fromhex(window)
  for off,opcode,desc in m.PREVIOUS: b[off:off+4]=bytes.fromhex(opcode)
  return bytes(b)
 def test_geometry(self):
  p=m.memory_geometry()
  self.assertEqual(p["inner_overrun_bytes_before"],24*1024*1024)
  self.assertEqual(p["unreserved_bytes_before"],0x17d9e00)
  self.assertEqual(p["virtual_increase_bytes"],256*1024*1024)
  self.assertEqual(p["alias_headroom_bytes_after"],192*1024*1024)
  self.assertEqual(m.ROOT_START+m.FIXED_SIZE,0x434000000)
  self.assertEqual(m.INNER_START+m.INNER_SIZE,0x425800000)
 def test_original_fingerprints_and_exact_five_bytes(self):
  old=self.make_fixture()
  for off,o,n,ctx in m.MOVZ:
   self.assertEqual(hashlib.sha256(old[off-24:off+40]).hexdigest(),ctx)
  new=m.patch_root_bytes(old)
  self.assertEqual(sum(a!=b for a,b in zip(old,new)),5)
  for off,o,n,_ in m.MOVZ:
   self.assertEqual(new[off:off+4],bytes.fromhex(n))
  for off,op,_ in m.PREVIOUS:
   self.assertEqual(new[off:off+4],bytes.fromhex(op))
 def test_reject_unrecognized_module(self):
  b=bytearray(self.make_fixture())
  b[0x225de0c:0x225de10]=b"\x00"*4
  with self.assertRaisesRegex(RuntimeError,"is not the five-cut"):
   m.patch_root_bytes(bytes(b))
 def test_no_shader_work_or_crash_nops(self):
  source=f.read_text()
  self.assertIn("base.make(source,output,report)",source)
  self.assertNotIn("nop(",source)
  for forbidden in ('subprocess.run(["xcodebuild"','dmsh_build.py','build_ipa_from_nsp.py'):
   self.assertNotIn(forbidden,source)
  self.assertEqual(m.SOURCE_RUN,44986770915)
