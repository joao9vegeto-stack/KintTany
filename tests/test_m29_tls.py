"""Host-only native PS3 TLS handler test against synthetic guest memory."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class M29TLSTests(unittest.TestCase):
 def test_guest_tls_copy_zero_and_r13(self):
  cc=shutil.which('clang') or shutil.which('cc')
  if not cc:self.skipTest('no host compiler')
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)
   args=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(ROOT/'tests'/'fixtures'),'-I',str(ROOT/'runtime'),
     str(ROOT/'runtime'/'ppu_bridge.c'),str(ROOT/'runtime'/'ppu_tls.c'),str(ROOT/'tests'/'host_ppu_tls.c'),'-o',str(p/'smoke')]
   c=subprocess.run(args,capture_output=True,text=True,timeout=30)
   self.assertEqual(c.returncode,0,c.stderr)
   r=subprocess.run([str(p/'smoke')],capture_output=True,text=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertIn('PASS: sys_initialize_tls',r.stdout)
