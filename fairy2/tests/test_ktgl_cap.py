"""Fail closed on KTGL's two matching capacity loads."""
from pathlib import Path
import importlib.util,sys,unittest
file=Path(__file__).resolve().parents[1]/"scripts/audit_ktgl_cap.py"
sys.path.insert(0,str(file.parent))
spec=importlib.util.spec_from_file_location("fairy2_ktglcap",file)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class Test(unittest.TestCase):
 def test_both_sites_and_cap(self):
  self.assertEqual([(x,reg) for x,_,reg in m.SITES],[(0x21b6924,8),(0x21b6954,25)])
  self.assertEqual(m.movz_x(8,0x10000000).hex(),"0800a2d2")
  self.assertEqual(m.movz_x(25,0x14000000).hex(),"1980a2d2")
  self.assertEqual(len(m.LIMITS),3)
 def test_invalid_build_refused(self):
  from tempfile import TemporaryDirectory
  with TemporaryDirectory() as tmp:
   p=Path(tmp)/"main.patched.bin"
   with self.assertRaisesRegex(RuntimeError,"original KTGL load"):
    m.insert_cap(p,bytes(0x21b6958+8),0x10000000)
 def test_mac_only(self):
  src=file.read_text()
  for needle in ('build_ipa.sh','xcodebuild','dmsh_build.py'):
   self.assertNotIn(needle,src)
  self.assertIn('exe=mac_host(',src)
  self.assertIn('proof=parse_probe(',src)
