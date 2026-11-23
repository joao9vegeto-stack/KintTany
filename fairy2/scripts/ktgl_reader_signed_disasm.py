#!/usr/bin/env python3
"""Read only: audited ARM64 KTGL v458752 reader and producer from pinned signed IPA.

No game assets, arbitrary binary dumps, or proprietary resources are published.
The target is the unchanged guest reader section of the actually crashing build.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path

REGIONS = (
 ("buffered-stream-full",0xc09514,0xc09728),
 ("adapter-original-forward",0xc09728,0xc09740),
 ("KTGL-resource-create",0xc10510,0xc10b90),
 ("chunk-producer-mode4",0xc10d80,0xc10ee8),
 ("direct-reader",0xc11b60,0xc11fc0),
 ("direct-resource-call",0xc11800,0xc119a0),
 ("direct-block-allocator",0xc119a0,0xc11b60),
 ("direct-failure-factory",0xc10b90,0xc10d80),
 ("mode4-codec",0xc0ef70,0xc0f0f0),
 ("G1T-header-native",0x60db9c,0x60dd10),
 ("G1T-validator",0x6120e0,0x6121dc),
 ("G1S-validator",0x6e7b60,0x6e7be8),
)
HOT = (0xc09514,0xc09554,0xc09594,0xc095c8,0xc09604,0xc09654,
       0xc0969c,0xc096dc,0xc09718,0xc09728,0xc11b60,
       0xc11f9c,0xc0ef8c,0xc0f0d4,0xc10d80)
def insist(ok, message):
    if not ok: raise ValueError("[Fairy2iOS STATIC READER] "+message)

def get_game_macho(ipa:Path)->bytes:
    with zipfile.ZipFile(ipa) as archive:
        game="DmGame0100B9801F872000"
        ending="/"+game+".framework/"+game
        matches=[p for p in archive.namelist() if p.endswith(ending)]
        insist(len(matches)==1,"expected one exact signed Fairy Tail 2 game Mach-O")
        info=archive.getinfo(matches[0])
        insist(20_000_000 < info.file_size < 350_000_000,
              "game executable unexpectedly small/large")
        with archive.open(info) as f: return f.read()

def get_sections(data:bytes):
    insist(len(data)>=32 and struct.unpack_from("<I",data)[0]==0xfeedfacf,
           "little endian Mach-O 64 required")
    cpu,ncmds,cmdsz=struct.unpack_from("<iII",data,4)[0],struct.unpack_from("<I",data,16)[0],struct.unpack_from("<I",data,20)[0]
    insist(cpu==0x0100000c and 1<=ncmds<=1000 and cmdsz<len(data),
           "expected AArch64 and bounded Mach-O load commands")
    off=32; sections={}
    for _ in range(ncmds):
        cmd,size=struct.unpack_from("<II",data,off)
        insist(size>=8 and off+size<=len(data),"bad Mach-O command")
        if cmd==0x19:
            insist(size>=72,"bad LC_SEGMENT_64")
            segname=data[off+8:off+24].split(b"\0",1)[0].decode("ascii","replace")
            count=struct.unpack_from("<I",data,off+64)[0]
            insist(size>=72+80*count,"truncated section list")
            for i in range(count):
                at=off+72+i*80
                sect=data[at:at+16].split(b"\0",1)[0].decode("ascii","replace")
                disk_size=struct.unpack_from("<Q",data,at+40)[0]
                disk_off=struct.unpack_from("<I",data,at+48)[0]
                if disk_size and disk_off:
                    insist(disk_size<len(data) and disk_off+disk_size<=len(data),
                           "section outside Mach-O")
                    sections[(segname,sect)]=(disk_off,disk_size)
        off+=size
    return sections

def audit(ipa:Path,expected_sha:str)->dict:
    import capstone
    sha=hashlib.sha256()
    with ipa.open("rb") as f:
        for block in iter(lambda:f.read(8*1024*1024),b""):sha.update(block)
    actual_sha=sha.hexdigest()
    insist(actual_sha==expected_sha,"signed IPA checksum mismatch")
    macho=get_game_macho(ipa)
    sections=get_sections(macho)
    insist(("__TEXT","__dmmainx0") in sections,"guest code RX section missing")
    xoff,xsize=sections[("__TEXT","__dmmainx0")]
    code=macho[xoff:xoff+xsize]
    insist(xsize>=max(r[2] for r in REGIONS),"guest reader offsets outside x0")
    md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN)
    md.detail=False
    out={"ipa_sha256":actual_sha,"macho_sha256":hashlib.sha256(macho).hexdigest(),
         "guest_x0_sha256":hashlib.sha256(code).hexdigest(),
         "guest_x0_size":xsize,"regions":[],"hot":[]}
    for name,first,last in REGIONS:
        raw=code[first:last]
        ins=list(md.disasm(raw,first))
        insist(len(ins)==(last-first)//4,"incomplete ARM64 disassembly in "+name)
        selected=[x for x in ins if
          (name in ("buffered-stream-full","adapter-original-forward","G1T-header-native","G1T-validator","G1S-validator","KTGL-resource-create","chunk-producer-mode4","direct-reader","direct-block-allocator","direct-resource-call","direct-failure-factory","mode4-codec"))
          or x.mnemonic.startswith(("bl","b.","cb","tb")) or
          x.address in HOT or x.address in range(first, min(first+0x40,last),4)]
        rows=[{"at":hex(x.address),"hex":x.bytes.hex(),
               "op":x.mnemonic+" "+x.op_str} for x in selected]
        out["regions"].append({"name":name,"start":hex(first),"end":hex(last),
             "instructions":len(ins),"disasm":rows})
    for at in HOT:
        word=code[at:at+4]
        ins=list(md.disasm(word,at))
        out["hot"].append({"at":hex(at),"word":word.hex(),
          "text":(ins[0].mnemonic+" "+ins[0].op_str) if ins else "not-decodable"})
    return out

def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("--ipa",type=Path,required=True)
    arg.add_argument("--expected-sha",required=True)
    arg.add_argument("--out",type=Path,required=True)
    opts=arg.parse_args()
    report=audit(opts.ipa,opts.expected_sha)
    opts.out.parent.mkdir(parents=True,exist_ok=True)
    opts.out.write_text(json.dumps(report,indent=2)+"\n")
    print("SOURCE IPA SHA256",report["ipa_sha256"])
    print("GUEST RX SHA256",report["guest_x0_sha256"])
    for reg in report["regions"]:
        print("\n=== KTGL FUNCTION",reg["name"],reg["start"],reg["end"],
              "instructions",reg["instructions"],"===")
        for instruction in reg["disasm"]:
            print(instruction["at"],instruction["hex"],instruction["op"])
    print("\nREAD ONLY, NO SHADERS, NO IPA BUILT")
if __name__=="__main__":main()
