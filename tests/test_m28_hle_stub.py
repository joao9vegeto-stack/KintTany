"""Synthetic-only HLE missing policy and PPC ABI callback test."""
import shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from make_hle_smoke import make
class HLEBridge(unittest.TestCase):
 def test_hle_import_fails_then_runs_handler(self):
  cc=shutil.which('clang') or shutil.which('cc')
  if not cc:self.skipTest('compiler absent')
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);source=p/'synthetic.c';make(source)
   args=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-label','-Wno-unused-function',
         '-I',str(ROOT/'tests'/'fixtures'),'-I',str(ROOT/'runtime'),str(source),
         str(ROOT/'runtime'/'ppu_bridge.c'),str(ROOT/'tests'/'host_hle_import.c'),'-o',str(p/'host')]
   comp=subprocess.run(args,capture_output=True,text=True,timeout=25)
   self.assertEqual(comp.returncode,0,comp.stderr)
   run=subprocess.run([str(p/'host')],capture_output=True,text=True,timeout=10)
   self.assertEqual(run.returncode,0,run.stderr)
   self.assertIn('PASS: import stub',run.stdout)
