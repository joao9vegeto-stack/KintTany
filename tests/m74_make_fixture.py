#!/usr/bin/env python3
"""Create a fully synthetic, public-domain PPC64 ELF fixture with two functions."""
import json
import struct
import sys
from pathlib import Path
def create(elf: Path, manifest: Path):
    d = bytearray(0x200)
    d[:7] = b"\x7fELF\x02\x02\x01"
    struct.pack_into(">HHI",d,16,2,21,1)
    struct.pack_into(">Q",d,24,0x10000)
    struct.pack_into(">Q",d,32,64)
    struct.pack_into(">HHH",d,52,64,56,1)
    struct.pack_into(">IIQQQQQQ",d,64,1,5,0x100,0x10000,0,0x20,0x20,0x1000)
    # bl 0x10010; blr | addi r3,r0,7; blr. Two separate AOT functions.
    for offset,word in ((0x100,0x48000011),(0x104,0x4e800020),
                        (0x110,0x38600007),(0x114,0x4e800020)):
        struct.pack_into(">I",d,offset,word)
    elf.write_bytes(d)
    manifest.write_text(json.dumps([
        {"start":"0x10000","end":"0x10008"},
        {"start":"0x10010","end":"0x10018"}
    ],indent=2)+"\n")
if __name__ == "__main__":
    create(Path(sys.argv[1]),Path(sys.argv[2]))
