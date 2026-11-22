import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import repack_full_resource_va as fix
class TestFullResourceVA(unittest.TestCase):
    def test_6g_geometry_5g_root_and_2g_ktgl(self):
        g=fix.memory_geometry()
        self.assertEqual(g["guest_reserve"],0x180000000)
        self.assertEqual(g["alias_after"],0x158000000)
        self.assertEqual(g["heap_after"],0x8000000)
        self.assertEqual(g["root_after"],0x140000000)
        self.assertEqual(g["root_free_after_initial_regions"],0x6ae00000)
        self.assertEqual(g["bin47_base"],0x3ed800000)
        self.assertEqual(g["ktgl_child_size"],0x80000000)
        self.assertTrue(g["physical_memory_pool_unchanged"])
    def test_branches_and_real_five_gigabyte_movz_movk(self):
        for i,(site,reg) in enumerate(fix.ROOT_SITES):
            cave=fix.CAVE+i*fix.CAVE_STRIDE
            for at,dest in [(site,cave),(cave+8,site+4)]:
                op=int.from_bytes(fix.branch_opcode(at,dest),"little")
                self.assertEqual(op & 0xfc000000,0x14000000)
                disp=op&0x3ffffff
                if disp&(1<<25):disp-=1<<26
                self.assertEqual(at+4*disp,dest)
            movz=0xd2c00020|reg;movk=0xf2a80000|reg
            self.assertEqual((movz>>5)&0xffff,1)
            self.assertEqual((movz>>21)&3,2)
            self.assertEqual((movk>>5)&0xffff,0x4000)
            self.assertEqual((movk>>21)&3,1)
            self.assertEqual((((movz>>5)&0xffff)<<32)+(((movk>>5)&0xffff)<<16),0x140000000)
            self.assertEqual(movz&31,reg);self.assertEqual(movk&31,reg)
    def test_code_cave_fallback_uses_only_actual_embedded_zeroes(self):
        # Mimic a final IPA whose Linux-stage preferred cave became occupied.
        raw=bytearray(fix.CAVE+0x110)
        raw[fix.CAVE:fix.CAVE+0x100]=bytes([0x42])*0x100
        for site,reg in fix.ROOT_SITES:raw[site:site+4]=fix.ROOT_OLD[reg]
        for site,op in fix.PRESERVE:raw[site:site+4]=bytes.fromhex(op)
        used=fix.choose_cave(bytes(raw))
        self.assertEqual(used,fix.CAVE_FIRST)
        patched,proof=fix.patch_bytes(bytes(raw))
        self.assertEqual(proof['code_cave'],f'main+0x{fix.CAVE_FIRST:x}')
        self.assertEqual(patched[fix.CAVE:fix.CAVE+0x100],bytes([0x42])*0x100)
    def test_exact_patch_sites_and_reject_repeat(self):
        source=bytearray(fix.CAVE+0x110)
        for site,reg in fix.ROOT_SITES:source[site:site+4]=fix.ROOT_OLD[reg]
        for site,op in fix.PRESERVE:source[site:site+4]=bytes.fromhex(op)
        source=bytes(source)
        patched,proof=fix.patch_bytes(source)
        self.assertEqual(proof["trampoline_count"],5)
        self.assertEqual(proof["new_root"],0x140000000)
        legal=set()
        for i,(site,reg) in enumerate(fix.ROOT_SITES):
            target=fix.CAVE+i*fix.CAVE_STRIDE
            legal.update(range(site,site+4))
            legal.update(range(target,target+12))
            self.assertEqual(patched[site:site+4],fix.branch_opcode(site,target))
            self.assertEqual(patched[target:target+4],(0xd2c00020|reg).to_bytes(4,"little"))
            self.assertEqual(patched[target+4:target+8],(0xf2a80000|reg).to_bytes(4,"little"))
            self.assertEqual(patched[target+8:target+12],fix.branch_opcode(target+8,site+4))
        changed={i for i,(a,b) in enumerate(zip(source,patched)) if a!=b}
        self.assertTrue(changed.issubset(legal))
        for site,op in fix.PRESERVE:self.assertEqual(patched[site:site+4],bytes.fromhex(op))
        with self.assertRaises(RuntimeError):fix.patch_bytes(patched)
if __name__=="__main__":unittest.main()
