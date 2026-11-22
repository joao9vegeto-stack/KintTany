import unittest,sys,importlib.util
from pathlib import Path
p=Path(__file__).resolve().parents[1]/"scripts/repack_global_memory.py"
sys.path.insert(0,str(p.parent))
spec=importlib.util.spec_from_file_location("global_mem",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Test(unittest.TestCase):
 def test_geometry(self):
  g=m.memory_geometry()
  self.assertEqual(g["guest_reserve"],5*1024**3)
  self.assertEqual(g["alias_after"],0x118000000)
  self.assertEqual(g["heap_after"],0x8000000)
  self.assertEqual(g["root_after"],0x100000000)
  self.assertEqual(g["root_extra_alias_bytes"],0x14200000)
  self.assertEqual(g["mapped_alias_budget"],0xc1500000)
  self.assertEqual(g["map_limit"],1)
 def test_five_movz(self):
  self.assertEqual(len(m.MOVZ),5)
  for pos,old,new in m.MOVZ:
   for op,target in ((old,0xd0000000),(new,0x100000000)):
    i=int.from_bytes(bytes.fromhex(op),"little")
    self.assertEqual(((i>>5)&65535)<<(16*((i>>21)&3)),target)
  self.assertEqual(len(m.PRESERVE),4)
 def test_only_native_framework_compiled(self):
  src=p.read_text()
  self.assertIn('"#define DM_GAME_MEM_MAP_LIMIT 1"',src)
  self.assertIn('"-target","DmShellGame"',src)
  self.assertIn('verify_main(built,guest_stamp)',src)
  self.assertIn('repack_ipa as menu',src)
  self.assertEqual(m.SOURCE_RUN,44988275455)
