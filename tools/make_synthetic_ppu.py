#!/usr/bin/env python3
"""Purely synthetic PowerPC64/Cell LV2 ELF fixture for testing the upstream PPU lifter."""
import argparse
from pathlib import Path
import struct

def create_elf():
    data=bytearray(0x2100)
    struct.pack_into(">16sHHIQQQIHHHHHH",data,0,b"\x7fELF\x02\x02\x01\x66"+bytes(8),2,21,1,0x20000,64,0x200,0,64,56,2,64,4,3)
    struct.pack_into(">IIQQQQQQ",data,64,1,5,0x1000,0x10000,0x10000,0x100,0x100,0x1000)
    struct.pack_into(">IIQQQQQQ",data,120,1,6,0x2000,0x20000,0x20000,0x100,0x100,0x1000)
    names=b"\0.text\0.opd\0.shstrtab\0"
    data[0x3c0:0x3c0+len(names)]=names
    struct.pack_into(">IIQQQQIIQQ",data,0x200+64,1,1,6,0x10000,0x1000,0x28,0,0,4,0)
    struct.pack_into(">IIQQQQIIQQ",data,0x200+128,7,1,3,0x20000,0x2000,0x10,0,0,8,0)
    struct.pack_into(">IIQQQQIIQQ",data,0x200+192,12,3,0,0,0x3c0,len(names),0,0,1,0)
    for i,w in enumerate([0x3860002a,0x4800001d,0x4e800020,0x60000000,0x60000000,0x60000000,0x60000000,0x60000000,0x38600007,0x4e800020]):
        struct.pack_into(">I",data,0x1000+4*i,w)
    struct.pack_into(">IIII",data,0x2000,0x10000,0x20080,0x10020,0x20080)
    return bytes(data)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_bytes(create_elf())
    print("Generated a synthetic 2-function PPC64 ELF; no game bytes")
