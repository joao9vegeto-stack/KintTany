"""Host synthetic executable tests for PPU bridge with test ABI mirror."""
import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from make_dispatch_smoke import generate
class BridgeTests(unittest.TestCase):
 def test_native_bridge(self):
  cc=shutil.which('clang') or shutil.which('cc')
  if not cc:self.skipTest('C compiler missing')
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);code=p/'dispatch.c'
   self.assertEqual(generate(code),3)
   args=[cc,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-label','-Wno-unused-function',
         '-O2','-I',str(ROOT/'tests'/'fixtures'),'-I',str(ROOT/'runtime'),
         str(code),str(ROOT/'runtime'/'ppu_bridge.c'),str(ROOT/'tests'/'host_ppu_bridge.c'),
         '-o',str(p/'smoke')]
   comp=subprocess.run(args,capture_output=True,text=True,timeout=30)
   self.assertEqual(comp.returncode,0,comp.stderr)
   run=subprocess.run([str(p/'smoke')],capture_output=True,text=True,timeout=12)
   self.assertEqual(run.returncode,0,run.stderr)
   self.assertIn('PASS: canonical PPU state',run.stdout)
