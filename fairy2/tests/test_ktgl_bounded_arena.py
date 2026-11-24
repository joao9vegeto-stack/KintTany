"""Execute actual ARM64 growth guards in Unicorn, including the old crash extent."""
import sys,struct,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import repack_ktgl_bounded_arena as a
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm64_const as R

def run_guard(i,cap,committed,request,step,block_size,expected):
    site,at,old,fail,code=a.make_stubs()[i]
    _,_,aligned,positive,_=a.SITES[i]
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    u.mem_map(0x227b000,0x2000)
    u.mem_map(a.CAVE&~0xfff,0x1000)
    u.mem_map(0x1000000,0x2000)
    obj=0x1000000;block=0x1001000
    u.mem_write(at,code)
    def put(addr,x):u.mem_write(addr,struct.pack("<Q",x))
    def setr(r,x):u.reg_write(getattr(R,"UC_ARM64_REG_X"+str(r)),x)
    def getr(r):return u.reg_read(getattr(R,"UC_ARM64_REG_X"+str(r)))
    put(obj+0x60,committed);put(obj+0x68,cap);put(obj+0x70,step)
    put(block+8,block_size);put(block+0x10,0x1122334455667788)
    setr(20,obj);setr(8,request);setr(9,0x12345678)
    setr(23,block if positive and not aligned else request if aligned and not positive else 0x9870)
    setr(25,block);setr(24,request);setr(22,request)
    setr(18,0xdeadbeef)
    before=u.mem_read(obj,0x2000)
    dest=[]
    def hook(uc,addr,size,user):
        if addr in (site+4,fail):
            dest.append(addr);uc.emu_stop()
    u.hook_add(UC_HOOK_CODE,hook)
    u.emu_start(at,0,count=100)
    assert dest==[site+4 if expected else fail],(i,cap,committed,request,step,block_size,dest)
    assert u.mem_read(obj,0x2000)==before,"guard mutated metadata"
    assert getr(18)==0xdeadbeef and getr(20)==obj
    if expected:
        if positive:assert getr(8 if aligned else 9)==0x1122334455667788
        else:assert getr(9 if aligned else 8)==committed
    return dest[0]

class TestArena(unittest.TestCase):
 def test_exact_device_overlap_and_new_extent(self):
    g=a.geometry()
    self.assertGreater(g["device_corrupt_block"],g["previous_child_end"])
    self.assertLess(g["device_corrupt_block"],g["new_child_end"])
    self.assertEqual(g["ktgl_child_size"],0xc0000000)
    self.assertEqual(g["root_free_after_initial_regions"],0x2ae00000)
 def test_negative_tail_guard(self):
    for i in (0,2):
      for cap in (0x80000000,0xc0000000):
        run_guard(i,cap,cap-0x100000,0x100000,0x100000,0,True)
        run_guard(i,cap,cap-0x100000,0x100001,0x100000,0,False)
        run_guard(i,cap,cap+1,1,0x100000,0,False)
      run_guard(i,0x80000000,0x82900000,0x100000,0x100000,0,False)
      run_guard(i,0xc0000000,0x82900000,0x100000,0x100000,0,True)
 def test_positive_tail_guard(self):
    for i in (1,3):
      for cap in (0x80000000,0xc0000000):
        # native growth: request 0x1800, old free 0x400, step 1MiB => 1MiB
        run_guard(i,cap,cap-0x100000,0x1800,0x100000,0x400,True)
        run_guard(i,cap,cap-0xfffff,0x1800,0x100000,0x400,False)
        run_guard(i,cap,cap+1,0x1800,0x100000,0x400,False)
        run_guard(i,cap,cap-0x100000,0x1800,0,0x400,False)
      run_guard(i,0xc0000000,0x82900000,0x880,0x100000,0x100,True)
      run_guard(i,0x80000000,0x82900000,0x880,0x100000,0x100,False)
 def test_unbounded_legacy(self):
    for i in range(4):run_guard(i,0,0x82900000,0x1000,0x100000,0x100,True)
if __name__=="__main__":unittest.main()
