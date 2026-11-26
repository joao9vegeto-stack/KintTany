"""Linux-only accelerated NXNative split, without omitting any source or key."""
import ctypes
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

LIB=None
REFERENCE=None
CHECKED=0
SPLIT=None
ORIGINAL_INIT=None

def native_decode(data):
    if len(data)<272 or data[:8]!=b"CRILAYLA":
        raise ValueError("not CRILAYLA")
    us,cs=struct.unpack_from("<II",data,8)
    if cs>len(data)-272:
        raise ValueError("CRILAYLA truncated input")
    # A valid stream emits at most 270+ bytes per 8-bit continuation.
    # This generous bound prevents a corrupt length from requesting GiBs.
    if us>cs*300+256:
        raise ValueError("CRILAYLA impossible expansion")
    out=ctypes.create_string_buffer(us+256)
    rc=LIB(data,len(data),out,len(out))
    if rc:
        raise ValueError(f"CRILAYLA native rejected corrupt stream ({rc})")
    return out.raw

def checked_decode(data):
    global CHECKED
    result=native_decode(data)
    # Compare actual game samples with the original reference implementation
    # in every worker, not just a synthetic stream.
    if CHECKED<3 and len(result)<=2*1024*1024:
        if result!=REFERENCE(data):
            raise RuntimeError("CRILAYLA native/reference mismatch; refusing shader split")
        CHECKED+=1
        if CHECKED==3:
            print(f"[Nier2iOS] CRILAYLA worker {os.getpid()}: 3 real entries byte-identical to NXNative Python",flush=True)
    return result

def fixture(bits,n):
    bits+="0"*(-len(bits)%8)
    payload=bytes(int(bits[i:i+8],2) for i in range(0,len(bits),8))[::-1]
    return b"CRILAYLA"+struct.pack("<II",n,len(payload))+payload+b"H"*256

def verify_decoder():
    import random
    rng=random.Random(42)
    for n in (0,1,3,256,8192):
        raw=rng.randbytes(n)
        data=fixture("".join("0"+f"{v:08b}" for v in raw[::-1]),n)
        if native_decode(data)!=REFERENCE(data) or native_decode(data)!=b"H"*256+raw:
            raise RuntimeError("CRILAYLA literal test failed")
    for raw,bits,n in (
        (b"ABC"*5,"".join("0"+f"{v:08b}" for v in b"CBA")+"1"+"0"*13+"11"+"110",15),
        (b"DEFABCDEF","".join("0"+f"{v:08b}" for v in b"FEDCBA")+"1"+f"{3:013b}"+"00",9),
        (b"A"*303,"".join("0"+f"{v:08b}" for v in b"AAA")+"1"+"0"*13+"11"+"111"+"11111"+"11111111"+"00000001",303),
    ):
        data=fixture(bits,n)
        if native_decode(data)!=REFERENCE(data) or native_decode(data)!=b"H"*256+raw:
            raise RuntimeError("CRILAYLA match test failed")
    try: native_decode(fixture("1"+"0"*13+"00",3))
    except ValueError: pass
    else: raise RuntimeError("CRILAYLA invalid backreference accepted")

def install():
    global LIB,REFERENCE,CHECKED
    import cpk
    if REFERENCE is None:
        REFERENCE=cpk.crilayla
    path=os.environ["NIER_CRILAYLA_LIB"]
    lib=ctypes.CDLL(path)
    fn=lib.nier_crilayla
    fn.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
    fn.restype=ctypes.c_int
    LIB=fn
    CHECKED=0
    cpk.crilayla=checked_decode

def worker_init(*args):
    import shader_split
    # Original initializer installs borrowed Unity trees and zstd dictionaries.
    if ORIGINAL_INIT is not None:
        ORIGINAL_INIT(*args)
    else:
        shader_split._pool_init(*args)
    install()

def cpu_workers():
    count=len(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else (os.cpu_count() or 2)
    try:
        quota,period=Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota!="max": count=min(count,max(1,(int(quota)+int(period)-1)//int(period)))
    except (OSError,ValueError): pass
    try:
        mem=int(Path("/sys/fs/cgroup/memory.max").read_text())
    except (OSError,ValueError):
        mem=int(next(l.split()[1] for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemTotal:")))*1024
    return max(1,min(count,8,max(1,(mem-1024**3)//(1536*1024**2))))

def main():
    global SPLIT,ORIGINAL_INIT
    # Same engine checkout, same source files/arguments/table generation.
    original=Path(sys.argv.pop(1)).resolve()
    engine=original.parents[3]
    for p in (original.parent,engine/"dm/tools",engine/"dm/games"):
        sys.path.insert(0,str(p))
    import shader_split
    SPLIT=shader_split
    ORIGINAL_INIT=shader_split._pool_init
    source=Path(__file__).with_name("crilayla.c")
    digest=hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache=Path("/content/nier/native-tools/crilayla")/digest
    cache.mkdir(parents=True,exist_ok=True)
    library=cache/"crilayla.so"
    if not library.is_file():
        temp=library.with_suffix(".part")
        subprocess.run(["gcc","-O3","-Wall","-Wextra","-Werror","-shared","-fPIC",str(source),"-o",str(temp)],check=True)
        temp.replace(library)
    os.environ["NIER_CRILAYLA_LIB"]=str(library)
    install()
    verify_decoder()
    shader_split._pool_init=worker_init
    jobs=cpu_workers()
    os.environ["J"]=str(jobs)
    print(f"[Nier2iOS] Native CRILAYLA verified against upstream; J={jobs} (CPU/RAM aware); scanning ALL inputs, original shader table gates retained.",flush=True)
    started=time.monotonic()
    shader_split.main()
    print(f"[Nier2iOS] Native full shader split completed in {time.monotonic()-started:.1f}s",flush=True)

if __name__=="__main__":
    main()
