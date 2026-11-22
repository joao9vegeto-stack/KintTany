import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import repack_ktgl_overlap as patch

class TestKTGL2GiBNoOverlap(unittest.TestCase):
    def test_exact_crashed_source(self):
        self.assertEqual(patch.SOURCE_RUN,44992666178)
        self.assertEqual(patch.SOURCE_SHA,
            "6b3803ac5359c724fb43781688c1e3eab7cb3b80dde723a64f73e945c0574c0c")
        self.assertEqual({x[0] for x in patch.MOVZ},{0x21b6924,0x21b6954})
    def test_live_nvn_pool_no_longer_overlaps_bin_table(self):
        g=patch.memory_geometry()
        self.assertEqual(g["old_ktgl_end"],0x3bd800000)
        self.assertEqual(g["gpu_pool_base"],0x3816ac000)
        self.assertEqual(g["gpu_pool_end"],0x3d20ac000)
        self.assertEqual(g["old_gpu_overflow_bytes"],0x148ac000)
        self.assertEqual(g["new_ktgl_end"],0x3ed800000)
        self.assertGreater(g["new_gpu_gap_bytes"],0)
        self.assertEqual(g["new_ktgl_end"],g["next_region_base"])
        self.assertEqual(g["all_initial_regions_end"],0x401200000)
        self.assertEqual(g["root_free_after_initial_regions"],0x2ae00000)
    def test_movz_both_producers(self):
        from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
        md=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
        for off,old,new in patch.MOVZ:
            src=list(md.disasm(bytes.fromhex(old),off))[0]
            dst=list(md.disasm(bytes.fromhex(new),off))[0]
            self.assertEqual(src.mnemonic,"mov")
            self.assertEqual(dst.mnemonic,"mov")
            self.assertTrue(src.op_str.endswith("#0x14000000"),src.op_str)
            self.assertTrue(dst.op_str.endswith("#0x20000000"),dst.op_str)
    def test_keep_parent_and_heap(self):
        kept={p:v for p,v in patch.PRESERVE}
        self.assertEqual(kept[0x2295a88],"1300a152")
        self.assertEqual(kept[0x21b6a74],"2200a052")
        self.assertEqual(kept[0x2295a50],"2100c0d2")
if __name__=="__main__": unittest.main()
