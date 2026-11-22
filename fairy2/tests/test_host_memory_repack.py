"""Static source and memory-budget regression checks (no Xcode needed)."""
import importlib.util
import unittest
from pathlib import Path
s=Path(__file__).resolve().parents[1]/"scripts"/"repack_host_memory.py"
spec=importlib.util.spec_from_file_location("fairy2_host_profile",s)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class HostMemoryRepackTests(unittest.TestCase):
    def test_capacity_real_fix(self):
        self.assertEqual(m.OLD_HEAP_CAP,128*1024*1024)
        self.assertEqual(m.NEW_HEAP_CAP,1024*1024*1024)
        self.assertLess(m.NEW_ALIAS,m.OLD_ALIAS)
        self.assertEqual(m.MEM_RESERVE,5*1024**3)
    def test_game_shader_compilation_absent(self):
        src=s.read_text()
        for forbidden in ("dmsh_build.py","build_shaders(","build_ipa_from_nsp.py"):
            self.assertNotIn(forbidden,src)
    def test_profile_mutation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"game.tsv"
            p.write_text("title_id\t"+m.TITLE_ID+"\nmem_reserve\t0x140000000\nmem_alias\t0x118000000\napp_pool\t0xCD500000\n")
            m.change_profile(p)
            self.assertEqual(m.profile_row(p,"mem_alias"),"0xe0000000")
            self.assertEqual(m.profile_row(p,"app_pool"),"0xCD500000")
    def test_reject_wrong_source_alias(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"game.tsv"
            p.write_text("mem_reserve\t0x140000000\nmem_alias\t0x80000000\n")
            with self.assertRaises(SystemExit):
                m.change_profile(p)
