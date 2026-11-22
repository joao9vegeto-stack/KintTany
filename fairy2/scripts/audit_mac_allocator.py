#!/usr/bin/env python3
"""Reproduce Fairy Tail 2's iOS allocator crash on an Apple Silicon Mac.

Consumes the same pinned Linux guest modules + RomFS; does NOT rebuild shaders,
rewrite binaries, call Xcode for iOS, or generate IPAs.
The 3GiB/128MiB/64KiB exact guest cuts are applied with the validated IPA scripts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TITLE="0100B9801F872000"
ENGINE="b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"
PROBES=[
 "main:227d2d0", # global region block allocator: requested byte count in x0
 "main:227d434", # global region allocator return in x19
 "main:227d448", # AllocateMemoryPages wrapper (x0 virtual addr, x1 bytes)
 "main:227d47c", # SDK result after AllocateMemoryPages
 "main:21b6710", # KTGL arena constructor receives candidate region in x1
 "main:21b6a80", # 32MiB arena allocation return in x0
 "main:21b6dbc", # subsequent 96B allocation return in x0
]
def insist(value,msg):
    if not value: raise RuntimeError("[Fairy2iOS MAC AUDIT] "+msg)

def run(command,*,cwd=None,env=None,log=None):
    print("[Fairy2iOS MAC AUDIT] +"," ".join(map(str,command)),flush=True)
    if log:
        with log.open("w") as f:
            p=subprocess.run(list(map(str,command)),cwd=cwd,env=env,
                             stdout=f,stderr=subprocess.STDOUT)
        if p.returncode: raise RuntimeError("command exited "+str(p.returncode)+", log "+str(log)+"\n"+log.read_text(errors="replace")[-4500:])
    else: subprocess.run(list(map(str,command)),cwd=cwd,env=env,check=True)

def patch_exact_game(work:Path, scripts:Path):
    sys.path.insert(0,str(scripts))
    from repack_region_cut import transform_main,SITES
    from repack_heap_128 import patch_heap_bytes
    from repack_align64 import patch_alignment_bytes
    image=work/"patched_v458752"/"main.patched.bin"
    insist(image.is_file(),"Linux-rewritten main not found")
    original=image.read_bytes()
    # This audit uses the EXACT same code paths shipped in the 64KiB IPA.
    cut,changes=transform_main(original)
    heap=patch_heap_bytes(cut)
    align=patch_alignment_bytes(heap)
    insist(len(changes)==5 and len(align)==len(original),"wrong binary patch count/size")
    expected={site:new for site,old,new,*_ in SITES}
    for off,new in expected.items(): insist(align[off:off+4]==bytes.fromhex(new),"3GiB patch absent")
    insist(align[0x2295a88:0x2295a8c]==bytes.fromhex("1300a152"),"128MiB heap patch absent")
    insist(align[0x21b6a74:0x21b6a78]==bytes.fromhex("2200a052"),"64KiB allocation patch absent")
    image.write_bytes(align)
    sdk=work/"patched_v458752"/"sdk.patched.bin"
    insist(sdk.is_file(),"Linux-rewritten SDK missing")
    sb=sdk.read_bytes()
    for off,needle in [
      (0x139468,"087ca052"),(0x1394fc,"097ca052"),
      (0x139654,"0b04a052"),(0x13965c,"0a04a052"),(0x139660,"0804a052"),
    ]: insist(sb[off:off+4]==bytes.fromhex(needle),f"missing verified SDK region cut at {off:#x}")
    return {
      "main_original_sha256":hashlib.sha256(original).hexdigest(),
      "main_repacked_sha256":hashlib.sha256(align).hexdigest(),
      "sdk_sha256":hashlib.sha256(sb).hexdigest(),
      "region_cuts":5,"heap128":True,"arena64k":True,"shader_compile":False
    }

def memory_profile(work:Path):
    p=work/"profile"/TITLE/"game.tsv"
    insist(p.is_file(),"prepared provisional game profile missing")
    lines=p.read_text().splitlines()
    out=[]
    seen=set()
    for line in lines:
        key=line.partition("\t")[0]
        if key=="mem_reserve":line="mem_reserve\t0x140000000";seen.add(key)
        if key=="mem_alias":line="mem_alias\t0xe0000000";seen.add(key)
        out.append(line)
    insist(seen=={"mem_alias","mem_reserve"},"wrong provisional memory profile")
    p.write_text("\n".join(out)+"\n")
    return p

def mac_host(engine:Path,env:dict,logs:Path):
    host=engine/"dm"/"host"
    insist(host.is_dir(),"pinned NXNative Mac host missing")
    prefix=f"gen/{TITLE}"
    run(["make","-s",f"GAME={TITLE}",f"{prefix}/game_profile.h",
         "gen/vpx/libvpx.a","gen/dav1d/libdav1d.a","host_msl"],
        cwd=host,env=env,log=logs/"host-prerequisites.log")
    run(["make","-s",f"GAME={TITLE}",f"{prefix}/dmhost"],
        cwd=host,env=env,log=logs/"mac-host-only-build.log")
    exe=host/prefix/"dmhost"
    insist(exe.is_file(),"no Mac host binary")
    return exe

def boot_one(exe,work,env,root:Path,label:str,alias:str,seconds:int):
    rd=root/label
    for dir in ["save","temp","msl"]: (rd/dir).mkdir(parents=True,exist_ok=True)
    romfs=work/"extract"/"v458752"/"RomFS.img"
    insist(romfs.stat().st_size==7889449169,"RomFS external file checksum/length handoff differs")
    profile=work/"profile"/TITLE
    game=work/"patched_v458752"
    be=dict(env)
    be.update({
       "DM_ROMFS":str(romfs),"DM_AOC_DIR":str(work/"aoc"),
       "DM_SAVE":str(rd/"save"),"DM_TEMP":str(rd/"temp"),
       "DM_MSL_DIR":str(rd/"msl"),"DM_NVN_SHMAP":str(profile/"shader_map.tsv"),
       "DM_ALIAS_SIZE":alias,
       "DM_SVC":"1","DM_REGIONS":str(rd/"regions.tsv"),
       "DM_PROBE":",".join(PROBES),"DM_PROBE_LIMIT":"70","DM_PROBE_ALL":"1",
       "DM_OPMODE":"1","DM_FPS_TARGET":"30",
    })
    path=rd/"boot.log"
    print(f"[Fairy2iOS MAC AUDIT] Launch {label}: alias={alias}, probes={len(PROBES)}",flush=True)
    started=time.monotonic()
    with path.open("w") as output:
        p=subprocess.Popen([str(exe),str(game)],cwd=rd,env=be,
                            stdout=output,stderr=subprocess.STDOUT)
        while p.poll() is None and time.monotonic()-started<seconds:
            time.sleep(.25)
        if p.poll() is None:
            p.terminate()
            try:p.wait(5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
    logs=path.read_text(errors="replace")
    critical=[
      line for line in logs.splitlines() if
      "[RED]" in line or "ResultInvalidParameter" in line or "CRASH sig" in line
      or "SetHeapSize" in line or "address region" in line
      or "alloc" in line.lower() and "PROBE" in line
    ]
    result={"label":label,"alias":alias,"exit":p.returncode,"duration_s":round(time.monotonic()-started,2),
            "nnmain":">>> nnMain" in logs,"crash":"CRASH sig=" in logs,
            "crash_site":"main+0x21b6dcc" in logs,
            "probe_blocks":logs.count("PROBE "), "error":"ResultInvalidParameter" in logs,
            "log":str(path),"region_file":str(rd/"regions.tsv"),"critical_tail":critical[-50:]}
    (rd/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print("[Fairy2iOS MAC AUDIT] Result:",json.dumps({k:result[k] for k in
           ["label","exit","nnmain","crash","crash_site","probe_blocks","error"]}),flush=True)
    print("[Fairy2iOS MAC AUDIT] Log tail:\n"+"\n".join(logs.splitlines()[-22:]),flush=True)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repository",type=Path,required=True)
    p.add_argument("--prepared",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--seconds",type=int,default=45)
    a=p.parse_args()
    repo=a.repository.resolve()
    prepared=json.loads(a.prepared.read_text())
    work=Path(prepared["work_dir"]).resolve()
    engine=repo/"engine"
    insist(prepared.get("project")=="Fairy2iOS" and
           prepared.get("engine_pin")==ENGINE and
           prepared.get("title_id")==TITLE,"wrong handoff; refusing another game")
    insist((repo/".upstream-ref").read_text().strip()==ENGINE,"engine pin drift")
    a.output.mkdir(parents=True,exist_ok=True)
    patch=patch_exact_game(work,repo/"fairy2"/"scripts")
    game=memory_profile(work)
    env=dict(os.environ,DM_GAMES_DIR=str(game.parent.parent),DM_GAMES_FIRST="1")
    exe=mac_host(engine,env,a.output)
    first=boot_one(exe,work,env,a.output,"iphone_alias", "0xe0000000",a.seconds)
    # The second run is a controlled test, not a new IPA. It distinguishes
    # fixed-size 3GiB reservation exhaustion from an unrelated bad pointer.
    control=boot_one(exe,work,env,a.output,"mac_64g_alias","0x1000000000",a.seconds)
    report={"project":"Fairy2iOS","test":"exact iOS guest binary, Mac native host-only replay",
            "prepared_hand_off":str(a.prepared),"repacked":patch,
            "no_game_shaders_compiled":True,"profiles":[first,control],
            "device_fix_verified":False}
    (a.output/"full-audit.json").write_text(json.dumps(report,indent=2)+"\n")
    print("[Fairy2iOS MAC AUDIT] Logs and report published; no IPA built.",flush=True)

if __name__=="__main__":
    main()
