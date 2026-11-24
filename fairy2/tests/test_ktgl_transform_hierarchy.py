"""Emulate the real ARM64 collect/reverse stubs, not a Python facsimile."""
import sys,struct,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import ktgl_transform_hierarchy as h
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm64_const as R
class TestHierarchy(unittest.TestCase):
 def execute(self,parents,start,count=None,corrupt_index=None):
    n=len(parents) if count is None else count
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    u.mem_map(0x208f000,0x1000);u.mem_map(0x2d6b000,0x1000)
    u.mem_map(0x100000,0x1000);u.mem_map(0x200000,0x1000)
    size=((len(parents)*48+4095)//4096)*4096 or 4096
    u.mem_map(0x300000,size)
    sp=0x100800;model=0x200000;header=0x200100;nodes=0x300000
    def reg(i,x):u.reg_write(getattr(R,"UC_ARM64_REG_X"+str(i)),x)
    def get(i):return u.reg_read(getattr(R,"UC_ARM64_REG_X"+str(i)))
    def put(a,fmt,x):u.mem_write(a,struct.pack(fmt,x))
    put(model,"<Q",header);put(header+4,"<h",n)
    for i,p in enumerate(parents):put(nodes+i*48+12,"<i",p)
    u.reg_write(R.UC_ARM64_REG_SP,sp)
    u.mem_write(sp+0x208,b"\xa5"*0x78)
    reg(26,model);reg(21,nodes);reg(24,start);reg(18,0xdeadbeef)
    for (_,_,at),data in zip(h.SITES,h.stubs()):u.mem_write(at,data)
    ends=[]
    def hook(uc,addr,size,user):
        if addr in (0x208f958,0x208fba0,0x208fbc4,0x208fbac):
            ends.append(addr);uc.emu_stop()
    u.hook_add(UC_HOOK_CODE,hook)
    def run(at,target=None):
        ends.clear();u.emu_start(at,0,count=1000000)
        assert len(ends)==1,(at,ends)
        if target is not None:assert ends[0]==target,(at,ends)
        return ends[0]
    run(h.SITES[0][2],0x208f958)
    depth=get(25)
    assert u.mem_read(sp+0x208,0x78)==b"\xa5"*0x78
    assert get(18)==0xdeadbeef
    out=[]
    if depth==0:
        run(h.SITES[1][2],0x208fbc4);return depth,out
    run(h.SITES[1][2],0x208fba0)
    if corrupt_index is not None:
        put(sp+8+(depth-1)*4,"<I",corrupt_index)
    for k in range(depth,0,-1):
        reg(25,k);reg(8,sp+8+k*4)
        if run(h.SITES[2][2])==0x208fbc4:break
        out.append(get(24))
    assert u.mem_read(sp+0x208,0x78)==b"\xa5"*0x78
    return depth,out
 def test_depth_187_no_stack_overflow_full_original_order(self):
    for n in (1,2,127,128,129,187,257):
        self.assertEqual(self.execute([-1]+list(range(n-1)),n-1),(n,list(range(n))))
 def test_real_crash_index_and_cycles(self):
    self.assertEqual(self.execute([-1],0x3f800000),(0,[]))
    self.assertEqual(self.execute([0],0),(0,[]))
    self.assertEqual(self.execute([1,0],0),(0,[]))
    self.assertEqual(self.execute([0x3f800000],0),(0,[]))
    self.assertEqual(self.execute([-1,0],1,corrupt_index=0x3f800000),(2,[]))
 def test_actual_count(self):
    self.assertEqual(self.execute([-1,0],1,count=1),(0,[]))
    self.assertEqual(self.execute([-1],0,count=0),(0,[]))
if __name__=="__main__":unittest.main()
