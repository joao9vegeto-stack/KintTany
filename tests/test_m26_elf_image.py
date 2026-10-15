"""Synthetic-only host ELF loader conformance."""
import shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from make_synthetic_ppu import create_elf
class M26ImageTests(unittest.TestCase):
 def test_private_free_elf_loader(self):
  cc=shutil.which('clang') or shutil.which('cc')
  if not cc:self.skipTest('no compiler')
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);elf=p/'SYNTHETIC.ELF';elf.write_bytes(create_elf())
   args=[cc,'-std=c11','-Wall','-Wextra','-Werror','-O2','-I',str(ROOT/'tests'/'fixtures'),'-I',str(ROOT/'runtime'),
         str(ROOT/'runtime'/'ppu_bridge.c'),str(ROOT/'runtime'/'elf_image.c'),str(ROOT/'tests'/'host_elf_image.c'),'-o',str(p/'image_smoke')]
   comp=subprocess.run(args,capture_output=True,text=True,timeout=25)
   self.assertEqual(comp.returncode,0,comp.stderr)
   r=subprocess.run([str(p/'image_smoke'),str(elf)],capture_output=True,text=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertIn('PASS: PS3 ELF64',r.stdout)
