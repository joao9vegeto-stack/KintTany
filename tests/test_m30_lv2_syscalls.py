"""Compile/run synthetic PPU SC ABI and missing syscalls."""
import shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from make_syscall_smoke import make
class M30SyscallTests(unittest.TestCase):
 def test_syscall_352_real_guest_memory_and_missing_handler(self):
  cc=shutil.which('clang') or shutil.which('cc')
  if not cc:self.skipTest('compiler unavailable')
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);guest=p/'sc.c';make(guest)
   cmd=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-label',
     '-I',str(ROOT/'tests'/'fixtures'),'-I',str(ROOT/'runtime'),
     str(guest),str(ROOT/'runtime'/'ppu_bridge.c'),str(ROOT/'runtime'/'lv2_smoke.c'),
     str(ROOT/'tests'/'host_lv2_syscall.c'),'-o',str(p/'sc')]
   build=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
   self.assertEqual(build.returncode,0,build.stderr)
   out=subprocess.run([str(p/'sc')],capture_output=True,text=True,timeout=10)
   self.assertEqual(out.returncode,0,out.stderr)
   self.assertIn('PASS: PPU sc',out.stdout)
