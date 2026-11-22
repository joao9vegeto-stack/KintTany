#!/usr/bin/env python3
"""Fairy2iOS: test KTGL's region capacity at its producer, using native Mac host.

The original runtime size stored at config+0xe0 is 0x62c00000, and main
main+0x21b6924 multiplies it by four: 0x18b000000 (6.17 GiB) inside a 3GiB
region. Never edit the crash site, SVC, or global heap. Override BOTH the
reservation's input and the allocator's matching capacity in the constructor.
This diagnostic does NOT compile shaders or create any IPA.
"""
from __future__ import annotations
import json
import re
import sys
import hashlib
from pathlib import Path
from audit_mac_allocator import (TITLE,ENGINE,PROBES,insist,patch_exact_game,
                                  memory_profile,mac_host,boot_one)

SITES=((0x21b6924,bytes.fromhex("687340f9"),8),
       (0x21b6954,bytes.fromhex("797340f9"),25))
LIMITS=(
 ("1GiB",0x10000000),
 ("1_25GiB",0x14000000),
 ("1_5GiB",0x18000000),
)
def movz_x(rd,value):
    insist(rd in (8,25) and value%0x10000==0 and
           0<value<=0xffff0000,"unsupported guest MOVZ cap")
    # movz Xd, imm16, lsl 16 (0xd2a00000)
    return int(0xd2a00000|((value>>16)<<5)|rd).to_bytes(4,"little")

def insert_cap(image:Path, baseline:bytes, value:int):
    insist(len(baseline)>0x21b6958,"not the game's v458752 main")
    data=bytearray(baseline)
    diffs=[]
    for offset,old,reg in SITES:
        insist(baseline[offset:offset+4]==old,
               f"original KTGL load at main+{offset:#x} differs")
        before=hashlib.sha256(baseline[offset-16:offset+24]).hexdigest()
        op=movz_x(reg,value)
        data[offset:offset+4]=op
        diffs.append({"offset":f"main+0x{offset:x}","old":old.hex(),
                      "new":op.hex(),"original_context_sha256":before})
    actual=sum(x!=y for x,y in zip(baseline,data))
    insist(0<actual<=8,"other guest code changed")
    image.write_bytes(data)
    return {"capacity_raw":value,"reserved_bytes":value*4,
            "changed_bytes":actual,"instructions":diffs,
            "main_sha256":hashlib.sha256(data).hexdigest()}

def parse_probe(log:Path):
    lines=log.read_text(errors="replace").splitlines()
    def at(s):
        return [x for x in lines if x.startswith("[dm] PROBE "+s+" ")]
    def field(line,name):
        m=re.search(r"(?:^| )"+re.escape(name)+r"=(0x[0-9a-f]+)",line)
        return int(m.group(1),16) if m else None
    sizes=[{"size":field(x,"x0")} for x in at("main+0x227d2d0")]
    returns=[{"pointer":field(x,"x19")} for x in at("main+0x227d434")]
    for i,row in enumerate(sizes):
        if i<len(returns):row.update(returns[i])
    arena=[field(x,"x0") for x in at("main+0x21b6a80")]
    err=[field(x,"x0") for x in at("main+0x227d47c")]
    return {
        "regions":sizes,"arena_32mib_return_values":arena,
        "page_commit_error_results":err,
        "first_oversized_region_failed":any(x["size"]>0xC0000000 and
                                            x.get("pointer")==0 for x in sizes),
        "arena_32mib_success":bool(arena and all(x and x>0x100000000 for x in arena)),
        "same_original_crash":"CRASH sig=11 addr=0x1ebc4 pc=main+0x21b6dcc" in "\n".join(lines),
        "nnMain":any(">>> nnMain" in x for x in lines),
        "first_present":any("frame=" in x or "frame 1" in x for x in lines),
        "errors":[x[:400] for x in lines if "[RED]" in x or "CRASH sig" in x][-25:]
    }

def main():
    import argparse,os
    p=argparse.ArgumentParser()
    p.add_argument("--repository",type=Path,required=True)
    p.add_argument("--prepared",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--seconds",type=int,default=45)
    a=p.parse_args()
    repo=a.repository.resolve()
    prepared=json.loads(a.prepared.read_text())
    insist(prepared.get("project")=="Fairy2iOS" and
           prepared.get("engine_pin")==ENGINE and
           prepared.get("title_id")==TITLE,"wrong game workspace")
    work=Path(prepared["work_dir"]).resolve()
    a.output.mkdir(parents=True,exist_ok=True)
    original_patches=patch_exact_game(work,repo/"fairy2"/"scripts")
    game=work/"patched_v458752"/"main.patched.bin"
    baseline=game.read_bytes()
    memory_profile(work)
    env=dict(os.environ,DM_GAMES_DIR=str(work/"profile"),DM_GAMES_FIRST="1")
    exe=mac_host(repo/"engine",env,a.output)
    outcomes=[]
    for label,cap in LIMITS:
        stamp=insert_cap(game,baseline,cap)
        run=boot_one(exe,work,env,a.output,label,"0xe0000000",a.seconds)
        proof=parse_probe(Path(run["log"]))
        entry={"label":label,"patch":stamp,"result":run,"proof":proof}
        outcomes.append(entry)
        (a.output/("report-"+label+".json")).write_text(
            json.dumps(entry,ensure_ascii=False,indent=2)+"\n")
        print("[Fairy2iOS KTGL CAP AUDIT]",label,
              "size",hex(cap*4),"arena",proof["arena_32mib_return_values"],
              "original_crash",proof["same_original_crash"],"error_codes",
              proof["page_commit_error_results"],flush=True)
    conclusion={"project":"Fairy2iOS","type":"real Mac guest-size limit experiments",
                "source_ipa_run":44983552364,"prior_patches":original_patches,
                "new_ipa_generated":False,"metal_shader_build":False,
                "outcomes":outcomes,
                "iphone_fix_verified":False}
    (a.output/"all-caps-audit.json").write_text(
        json.dumps(conclusion,ensure_ascii=False,indent=2)+"\n")
    print("[Fairy2iOS KTGL CAP AUDIT] Completed all real host experiments.",flush=True)

if __name__=="__main__":main()
