"""Game-free PPU thread ID HLE unit test with bounded guest memory."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class M36ThreadId(unittest.TestCase):
    def test_preserve_real_caller_identity(self):
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('no host compiler')
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'host'
            args=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                  '-I',str(ROOT/'tests'/'fixtures'),'-I',str(ROOT/'runtime'),
                  str(ROOT/'runtime'/'ppu_bridge.c'),
                  str(ROOT/'runtime'/'ppu_thread_services.c'),
                  str(ROOT/'tests'/'host_thread_id.c'),'-o',str(out)]
            b=subprocess.run(args,capture_output=True,text=True,timeout=25)
            self.assertEqual(b.returncode,0,b.stderr)
            r=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('PASS: sys_ppu_thread_get_id',r.stdout)
