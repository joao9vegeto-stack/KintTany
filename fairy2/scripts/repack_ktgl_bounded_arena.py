#!/usr/bin/env python3
"""Correct the actual KTGL sparse-heap extent, not G1T/G1S resource bytes.

v458752 iPhone PDRK build: main+227be20 unlink writes through a bogus link.
Allocator x20+0x20=36d800000, x20+0x10=828ffd80, block x23=3eda3ac90.
The 2GiB child ended at 3ed800000. Constructor main+21b6808 stores the
virtual capacity at inner+0x68 and growth granularity at +0x70; +0x60
is committed extent. The four native grow paths ignored +0x68. The
game's original 6.17GiB reservation hid this assumption on Switch.
Fit a 3GiB child in the existing 5GiB root and check each growth against
the actual constructor cap BEFORE unlinking or committing anything.
"""
from __future__ import annotations
import argparse,hashlib,json,struct
from pathlib import Path
import repack_ktgl_coherent_config as coherent
import repack_ktgl_pdrk_direct_io as pdrk

base=coherent.base
CAP=0xc0000000
UNITS=CAP//4
OUT="Fairy2iOS-FairyTail2-KTGL-BoundedArena.ipa"
CAVE=0x2d6b100
STRIDE=0x100
# site, original instruction, aligned path?, existing-tail-free path?, fail
SITES=(
 (0x227bcdc,"883240f9",False,False,0x227bc14),
 (0x227be14,"e90a40f9",False,True,0x227bc14),
 (0x227c67c,"893240f9",True,False,0x227c2f4),
 (0x227c5ac,"280b40f9",True,True,0x227c2f4),
)
# Constructor and exact growth arithmetic, from signed RX run 45348293297.
WITNESSES={
 0x21b67e4:"d6f67ed3", # x22 = capacity units * 4
 0x21b6808:"966607a9", # store cap and growth step at inner +68,+70
 0x21b6828:"882a01a9", # initial size at inner +10
 0x21b683c:"993600f9", # initial committed extent at inner +60
 0x227bcd8:"167d0a9b", # x22 = growth length
 0x227bf54:"8a3a40f9", # load growth step, positive tail case
 0x227bf5c:"0801098b",
 0x227bf68:"0809ca9a",
 0x227bf6c:"167d0a9b",
 0x227c678:"577d099b", # x23 = growth length
 0x227c770:"893a40f9",
 0x227c78c:"1781899a",
 0x227be20:"2a0d00f9", # crashing unlink store; NEVER patch it
 0x227bc14:"e0031faa", # native unaligned NULL return
 0x227c2f4:"e0031faa", # native aligned NULL return
}
def require(ok,msg):
    base.require(ok,msg)

def geometry():
    g=base_geometry()
    old_base=0x36d800000
    old_end=old_base+0x80000000
    new_end=old_base+CAP
    observed=0x3eda3ac90
    committed=0x828ffd80
    require(old_end==0x3ed800000 and observed>=old_end and
            committed>0x80000000,"old overlap witness differs from device")
    require(old_base+committed<new_end and observed+32<new_end,
            "new child fails observed peak")
    tail=g["initial_regions_end"]+(CAP-0x80000000)
    free=g["root_end"]-tail
    require(new_end==0x42d800000 and tail==0x441200000 and
            free==0x2ae00000 and tail<g["root_end"]<=g["alias_end"],
            "3GiB child and following arenas do not fit 5GiB root")
    g.update(ktgl_child_size=CAP,bin47_base=new_end,
             bin47_alias_offset=new_end-g["alias_base"]+0x178,
             initial_regions_end=tail,root_free_after_initial_regions=free,
             previous_child_end=old_end,new_child_end=new_end,
             device_corrupt_block=observed,device_old_extent=committed,
             observed_overrun_bytes=observed-old_end,
             original_child_bytes=0x18b000000)
    return g

base_geometry=base.memory_geometry
def ldr(rd,rn,offset):
    assert offset%8==0 and 0<=offset<32768
    return 0xf9400000|((offset//8)<<10)|(rn<<5)|rd
def add(rd,rn,rm):return 0x8b000000|(rm<<16)|(rn<<5)|rd
def subs(rd,rn,rm):return 0xeb000000|(rm<<16)|(rn<<5)|rd
def mvn(rd,rm):return 0xaa200000|(rm<<16)|(31<<5)|rd
def udiv(rd,rn,rm):return 0x9ac00800|(rm<<16)|(rn<<5)|rd
def mul(rd,rn,rm):return 0x9b007c00|(rm<<16)|(rn<<5)|rd
def csel(rd,rn,rm,cond):return 0x9a800000|(rm<<16)|(cond<<12)|(rn<<5)|rd
def movz16(rd,value):
    assert value%65536==0 and 0<=value<=0xffff0000
    return (0xd2a00000|((value>>16)<<5)|rd).to_bytes(4,"little")

class Asm:
    def __init__(self,start):self.start=start;self.words=[];self.labels={};self.fix=[]
    def emit(self,w):self.words.append(w)
    def label(self,l):self.labels[l]=len(self.words)
    def cond(self,l,c):
        self.fix.append((len(self.words),l,0x54000000|c));self.emit(0)
    def cbz(self,l,r):
        self.fix.append((len(self.words),l,0xb4000000|r));self.emit(0)
    def jump(self,to):
        self.emit(int.from_bytes(base.branch_opcode(self.start+len(self.words)*4,to),"little"))
    def finish(self):
        for i,l,w in self.fix:
            delta=self.labels[l]-i
            assert -(1<<18)<=delta<(1<<18)
            self.words[i]=w|((delta&0x7ffff)<<5)
        return b"".join(struct.pack("<I",w) for w in self.words)

def make_stubs():
    result=[]
    for i,(site,opcode,aligned,positive,fail) in enumerate(SITES):
        at=CAVE+i*STRIDE
        a=Asm(at)
        # Scratch x12-x14 are caller temporaries; preserve live x8/x9 and
        # x19-x26, SP/LR, and never use reserved Apple x18.
        a.emit(ldr(12,20,0x68)) # immutable per-allocator max extent
        a.cbz("allow",12)       # preserve older unbounded instances
        if positive:
            # Reproduce EXACT arithmetic from each native growth path BEFORE
            # any unlink. Current native step is already alignment-adjusted.
            a.emit(ldr(12,20,0x70))
            a.cbz("deny",12)
            a.emit(ldr(13,25 if aligned else 23,8))
            a.emit(mvn(13,13))
            a.emit(add(13,24 if aligned else 8,13))
            a.emit(add(13,13,12))
            a.emit(udiv(13,13,12))
            a.emit(mul(14,13,12))
            if aligned:
                a.emit(subs(31,14,12))
                a.emit(csel(14,14,12,8)) # max(growth,step)
            a.emit(ldr(12,20,0x68))
            grow=14
        else:
            grow=23 if aligned else 22
        a.emit(ldr(13,20,0x60))
        a.emit(subs(12,12,13)) # cap - committed, detect underflow
        a.cond("deny",3)       # LO: existing extent already beyond capacity
        a.emit(subs(31,grow,12))
        a.cond("deny",8)       # HI: grow crosses child's own reservation
        a.label("allow")
        a.emit(int.from_bytes(bytes.fromhex(opcode),"little"))
        a.jump(site+4)
        a.label("deny")
        a.jump(fail)           # existing NULL result, before list mutation
        data=a.finish()
        require(len(data)<=STRIDE,"allocator guard exceeds its code cave")
        result.append((site,at,opcode,fail,data))
    return result

def modify(raw,stamp):
    out,proof=old_patch(raw,stamp)
    out=bytearray(out)
    require(out[coherent.STUB_AT:coherent.STUB_AT+4]==coherent.STUB_MOVZ,
            "old coherent capacity producer differs")
    out[coherent.STUB_AT:coherent.STUB_AT+4]=movz16(8,UNITS)
    for at,opcode in WITNESSES.items():
        require(out[at:at+4].hex()==opcode,f"wrong original allocator at {at:#x}")
    guards=[]
    for site,at,opcode,fail,data in make_stubs():
        require(out[site:site+4].hex()==opcode,f"wrong growth path {site:#x}")
        require(out[at:at+STRIDE]==bytes(STRIDE),"guard cave is occupied")
        out[site:site+4]=base.branch_opcode(site,at)
        out[at:at+len(data)]=data
        guards.append({"site":hex(site),"original":opcode,"stub":hex(at),
          "size":len(data),"sha256":hashlib.sha256(data).hexdigest(),
          "native_failure":hex(fail),"before_commit_or_unlink":True})
    proof.update(new_capacity_bytes=CAP,
        new_one_shared_source="first consumer writes 0x30000000 units; second reloads shared config",
        staged_stub=out[coherent.STUB_AT:coherent.STUB_AT+12].hex(),
        allocation_bound_guards=guards,
        native_capacity_field="inner+0x68",native_committed_field="inner+0x60",
        original_allocator_crash_instruction_unchanged=True)
    return bytes(out),proof

old_patch=coherent.coherent_patch
old_verify=coherent.verify_main
def verify(exe,stamp):
    old_verify(exe,stamp)
    _,raw=base.main_sections(exe)
    require(raw[coherent.STUB_AT:coherent.STUB_AT+4]==movz16(8,UNITS),
            "3GiB child capacity lost")
    for site,at,opcode,fail,data in make_stubs():
        require(raw[site:site+4]==base.branch_opcode(site,at) and
                raw[at:at+len(data)]==data,"allocator guard changed after signing")
    for at,opcode in WITNESSES.items():
        require(raw[at:at+4].hex()==opcode,"original constructor/growth code changed")

def make(source,source_report,repo,out):
    base.memory_geometry=geometry
    coherent.coherent_patch=modify
    coherent.verify_main=verify
    pdrk.OUT_NAME=OUT
    try:
        report=pdrk.make(source,source_report,repo,out)
    finally:
        base.memory_geometry=base_geometry
        coherent.coherent_patch=old_patch
        coherent.verify_main=old_verify
    report.update(method="KTGL sparse allocator: 3GiB child and four pre-unlink/pre-map bounds checks; retain PDRK direct IO compatibility",
        bounded_ktgl_allocator_candidate=True,allocator_growth_guard_count=4,
        old_device_extent=0x828ffd80,old_device_corrupt_block=0x3eda3ac90,
        new_child_bytes=CAP,bin47_alias_offset=hex(geometry()["bin47_alias_offset"]),
        no_corrupt_pointer_repair=True,gameplay_verified=False)
    (out/"ktgl-pdrk-direct-io-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("FAIRY2 BOUNDED KTGL ALLOCATOR",report["output_ipa_sha256"],flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-ipa",type=Path,required=True)
    p.add_argument("--source-report",type=Path,required=True)
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    make(a.source_ipa,a.source_report,a.repo.resolve(),a.output)
