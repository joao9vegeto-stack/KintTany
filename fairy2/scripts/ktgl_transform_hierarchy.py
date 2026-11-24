"""Bound the original KTGL model transform traversal without truncating valid trees.
Source evidence: signed main disassembly, runs 45355242815/45355405617.
The old 128-u32 stack array overflowed at depth >128; x25=186 and w24=1.0f
bits on the A19 Pro. x9 is sign-extended index * 48, NOT a VA constant.
Use the real signed 16-bit node count in [[model]]+4, proven by caller
10b0e18. Keep native matrices/quaternions and the original fixed scratch.
Long chains rewalk parents from the saved first node; short chains keep
the fast original cached indices. Invalid/cyclic chains never write/read
outside the model or stack; use the initialized base transform if collection
fails, not a synthetic identity. If a chain changes during traversal, stop
before dereferencing an invalid record. No extra stack or guest allocations.
"""
import struct,hashlib
from repack_ktgl_bounded_arena import Asm,ldr,add,subs,mul
import repack_full_resource_va as base

SITES=((0x208f930,"f9031faa",0x2d6b500),
       (0x208fa0c,"65000014",0x2d6b600),
       (0x208fba8,"18c15fb8",0x2d6b700))
WITNESSES={0x208f8d0:"ff4308d1",0x208f940:"0a57289b",
           0x208f944:"387939b8",0x208f94c:"4a0d40b9",
           0x208f954:"6affff36",0x208fa34:"002140bd",
           0x208fbb0:"ec11c197",0x10b0e18:"0809c079",
           0x208f8e0:"1a0040f9",0x208fbc4:"ff430891"}
def movw(rd,rn):return 0x2a0003e0|(rn<<16)|rd
def movx(rd,rn):return 0xaa0003e0|(rn<<16)|rd
def imm(rd,n):return 0x52800000|(n<<5)|rd
def addi(rd,rn,n):return 0x91000000|(n<<10)|(rn<<5)|rd
def subi(rd,rn,n):return 0xd1000000|(n<<10)|(rn<<5)|rd
def cmpi(r,n):return 0xf100001f|(n<<10)|(r<<5)
def cmpw(r,m):return 0x6b00001f|(m<<16)|(r<<5)
def ldrw(rd,rn,n):return 0xb9400000|((n//4)<<10)|(rn<<5)|rd
def strw(rd,rn,n):return 0xb9000000|((n//4)<<10)|(rn<<5)|rd
def ldrshw(rd,rn,n):return 0x79c00000|((n//2)<<10)|(rn<<5)|rd
def smaddl(rd,rn,rm,ra):return 0x9b200000|(rm<<16)|(ra<<10)|(rn<<5)|rd
def local(a,label):
    a.fix.append((len(a.words),label,0x5400000e));a.emit(0)
def tbnz(a,label,r,bit):
    # Asm.finish uses imm19; TB has imm14, so use a separate local fix.
    a.tb.append((len(a.words),label,r,bit));a.emit(0)
def finish(a):
    for i,l,r,bit in getattr(a,"tb",[]):
        delta=a.labels[l]-i
        assert -(1<<13)<=delta<(1<<13)
        a.words[i]=0x37000000|((bit&31)<<19)|((bit>>5)<<31)|((delta&0x3fff)<<5)|r
    return a.finish()
def stubs():
    a=Asm(SITES[0][2]);a.tb=[]
    a.emit(movx(25,31));a.emit(strw(24,31,0))
    a.cbz("bad",26);a.emit(ldr(10,26,0));a.cbz("bad",10)
    a.emit(ldrshw(11,10,4));a.emit(0x7100017f) # cmp w11,#0
    a.cond("bad",13) # LE
    a.emit(strw(11,31,4))
    a.emit(addi(9,31,8));a.emit(imm(8,48))
    a.label("loop")
    a.emit(cmpw(24,11));a.cond("bad",2) # HS (negative also rejected)
    a.emit(subs(31,25,11));a.cond("bad",2) # cycle/too many nodes
    a.emit(cmpi(25,128));a.cond("nocache",2)
    a.emit(0xb8397938) # original str w24,[x9,x25,lsl #2]
    a.label("nocache")
    a.emit(smaddl(10,24,8,21))
    a.emit(addi(25,25,1))
    a.emit(ldrw(24,10,12))
    tbnz(a,"done",24,31)
    local(a,"loop")
    a.label("bad");a.emit(movx(25,31))
    a.label("done");a.jump(0x208f958)
    collect=finish(a)
    a=Asm(SITES[1][2])
    a.cbz("empty",25);a.jump(0x208fba0)
    a.label("empty");a.jump(0x208fbc4)
    begin=a.finish()
    a=Asm(SITES[2][2])
    a.emit(ldrw(13,31,4))
    a.emit(subs(31,25,13));a.cond("bad",8) # depth exceeds model count
    a.cbz("bad",25)
    a.emit(cmpi(25,128));a.cond("cached",9) # LS
    a.emit(ldrw(24,31,0))
    a.emit(subi(11,25,1));a.emit(imm(12,48))
    a.label("walk")
    a.emit(cmpw(24,13));a.cond("bad",2)
    a.cbz("check",11)
    a.emit(smaddl(10,24,12,21));a.emit(ldrw(24,10,12))
    a.emit(subi(11,11,1));local(a,"walk")
    a.label("cached");a.emit(0xb85fc118) # ldur w24,[x8,#-4]
    a.label("check");a.emit(cmpw(24,13));a.cond("bad",2)
    a.jump(0x208fbac)
    a.label("bad");a.jump(0x208fbc4)
    reverse=a.finish()
    return (collect,begin,reverse)

def apply(raw):
    out=bytearray(raw);records=[]
    for at,word in WITNESSES.items():
        base.require(out[at:at+4].hex()==word,f"transform original opcode changed at {at:#x}")
    for (site,word,at),data in zip(SITES,stubs()):
        base.require(out[site:site+4].hex()==word,"wrong transform build")
        base.require(len(data)<=0x100 and out[at:at+0x100]==bytes(0x100),"transform RX cave occupied")
        out[site:site+4]=base.branch_opcode(site,at);out[at:at+len(data)]=data
        records.append({"site":hex(site),"cave":hex(at),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
    return bytes(out),{"sites":records,"native_node_count":"[[model]]+4 signed int16",
      "fast_path_cached_nodes":128,"long_path":"reverse rewalk, no truncation",
      "max_native_node_count":32767,"invalid_hierarchy":"native base transform, no out-of-range reads",
      "original_transform_math_unchanged":True}

def verify(raw):
    for (site,word,at),data in zip(SITES,stubs()):
        base.require(raw[site:site+4]==base.branch_opcode(site,at) and raw[at:at+len(data)]==data,"transform guard missing")
    for at,word in WITNESSES.items():
        base.require(raw[at:at+4].hex()==word,"transform math or source witness changed")
