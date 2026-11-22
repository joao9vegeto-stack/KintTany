#!/usr/bin/env python3
"""Fairy2iOS coherent repair: reserve the full 2GiB KTGL region before the following arena, keeping the Metal shaders.

Corrects two interacting defects seen across three A19 Pro crash logs:
- restored 128MiB heap / 4.375GiB alias partition within 5GiB VA; main's
  root allocator uses 4GiB of it, not a succession of 3/3.25GiB bounds;
- compiles NXNative SVC MapPhysicalMemory budget (mem_map_limit=on),
  letting the SDK return its cached pages on ResultLimitReached, as on Horizon.

Builds the iOS native framework host ONLY, HookLink2iOS-style. All source
guest sections are reembedded verbatim except five verified main MOVZs.
Neither the NXNative guest rewriter nor Metal shader compiler is called.
"""
from __future__ import annotations
import argparse,hashlib,json,os,plistlib,re,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
import repack_host_memory as hook

TITLE="0100B9801F872000"
FRAMEWORK="DmGame"+TITLE+".framework"
SOURCE_RUN=44992666178
SOURCE_SHA="6b3803ac5359c724fb43781688c1e3eab7cb3b80dde723a64f73e945c0574c0c"
SOURCE_SIZE=1622226533
SHADER_SHA="ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b"
OUT_NAME="Fairy2iOS-FairyTail2-KTGL-2GiB-NoOverlap.ipa"
# The game shifts these two capacity producers left by two bits.
# 0x14000000 << 2 (1.25GiB) was incorrect. 0x20000000 << 2 is 2GiB.
MOVZ=((0x21b6924,"0880a2d2","0800a4d2"),
      (0x21b6954,"1980a2d2","1900a4d2"))
PRESERVE=((0x2295a88,"1300a152"),
          (0x21b6a74,"2200a052"),
          (0x5f1b9c,"2900c0d2"),
          (0x1d700bc,"2900c0d2"),
          (0x225de0c,"2900c0d2"),
          (0x2295a44,"2900c0d2"),
          (0x2295a50,"2100c0d2"))

def require(ok,message):
    if not ok: raise RuntimeError("[Fairy2iOS GLOBAL] "+message)

def memory_geometry():
    # The eight sequential KTGL allocs measured in run 44986356916 and
    # the real iPhone A19 Pro pool boundaries in log.txt (22-Nov-2026).
    root=0x32c000000
    first=root+0x41800000   # 300+200+260+192+96 MiB preceding regions
    original=0x50000000      # 1.25GiB old sixth region
    corrected=0x80000000     # 2GiB full inner child extent
    gpu=0x3816ac000
    gpu_bytes=0x50a00000    # 1290 MiB active NVN pool
    next_bytes=0x13000000  # 304 MiB next arena, whose bin table was corrupted
    tail_bytes=0xa00000    # 10 MiB last initial arena
    old_end=first+original
    new_end=first+corrected
    root_end=root+0x100000000
    gpu_end=gpu+gpu_bytes
    final_end=new_end+next_bytes+tail_bytes
    require(first==0x36d800000 and old_end==0x3bd800000,
            "old KTGL and next free-bin table base disagree with iPhone")
    require(gpu_end==0x3d20ac000 and
            gpu_end-old_end==0x148ac000,
            "GPU pool overflow into next bin table must match exact log")
    require(new_end==0x3ed800000 and new_end>gpu_end,
            "corrected KTGL child still overlaps NVN GPU pool")
    require(final_end==0x401200000 and
            final_end < root_end == 0x42c000000,
            "all sequential arenas must fit 4GiB enclosing root")
    return {"guest_reserve":0x140000000,"alias_after":0x118000000,
            "heap_after":0x8000000,"root_after":0x100000000,
            "root_extra_alias_bytes":0x14200000,
            "mapped_alias_budget":0xc1500000,"map_limit":1,
            "old_ktgl_capacity":original,"new_ktgl_capacity":corrected,
            "old_ktgl_base":first,"old_ktgl_end":old_end,
            "new_ktgl_base":first,"new_ktgl_end":new_end,
            "gpu_pool_base":gpu,"gpu_pool_size":gpu_bytes,"gpu_pool_end":gpu_end,
            "old_gpu_overflow_bytes":gpu_end-old_end,
            "new_gpu_gap_bytes":new_end-gpu_end,
            "next_region_base":new_end,"next_region_bytes":next_bytes,
            "tail_region_bytes":tail_bytes,
            "all_initial_regions_end":final_end,"root_end":root_end,
            "root_free_after_initial_regions":root_end-final_end,
            "bin47_alias_offset":0xc5800178,
            "no_overlapping_virtual_regions":True}

def profile_adjust(path:Path,canonical:bool):
    items=path.read_text().splitlines()
    fields={x.split("\t")[0]:x.split("\t",1)[1].strip() for x in items
            if "\t" in x and not x.startswith("#")}
    require(fields.get("mem_reserve")=="0x140000000","old 5GiB AS missing")
    require(fields.get("mem_alias") in ("0x118000000", "0xe0000000"),
            "wrong canonical/runtime source alias")
    out=[];found=False
    for line in items:
        key=line.partition("\t")[0]
        if key=="mem_alias":line="mem_alias\t0x118000000"
        if key=="mem_map_limit":
            found=True;line="mem_map_limit\t"+("on" if canonical else "1")
        out.append(line)
    if not found:out.append("mem_map_limit\t"+("on" if canonical else "1"))
    path.write_text("\n".join(out)+"\n")

def main_section(exe:Path):
    obj=hook.otool_sections(exe).get(("__TEXT","__dmmainx0"))
    require(bool(obj) and obj["size"]>0x2295a50+64,"missing verified embedded main")
    with exe.open("rb") as f:
        f.seek(obj["offset"]);data=f.read(obj["size"])
    require(len(data)==obj["size"],"guest section truncated")
    return obj["offset"],data

def patch_main(exe:Path,src_report:dict):
    off,raw=main_section(exe)
    root=(src_report.get("guest_root_patch") or {})
    expected=root.get("after_sha256")
    require(bool(expected) and hashlib.sha256(raw).hexdigest()==expected,
            "source embedded guest SHA differs from device-tested conservative IPA")
    for offset,old,new in MOVZ:
        require(raw[offset:offset+4]==bytes.fromhex(old),
                f"expected 1.25GiB KTGL producer missing at main+0x{offset:x}")
    for offset,opcode in PRESERVE:
        require(raw[offset:offset+4]==bytes.fromhex(opcode),
                f"prior root/heap/align patch lost at main+0x{offset:x}")
    corrected=bytearray(raw)
    for offset,old,new in MOVZ:
        corrected[offset:offset+4]=bytes.fromhex(new)
    actual=sum(x!=y for x,y in zip(raw,corrected))
    require(actual==4,"exactly 2 MOVZ must change, four bytes total")
    with exe.open("r+b") as f:
        f.seek(off)
        require(f.read(len(raw))==raw,"guest changed after validation")
        f.seek(off);f.write(corrected)
    return {"before_sha256":expected,"after_sha256":hashlib.sha256(corrected).hexdigest(),
            "old_region_bytes":0x50000000,"new_region_bytes":0x80000000,
            "byte_changes":actual,"instructions_changed":2,
            "other_global_4g_memory_fixes_preserved":True}
def verify_main(exe:Path,stamp:dict):
    _,data=main_section(exe)
    require(hashlib.sha256(data).hexdigest()==stamp["after_sha256"],
            "repacked ARM64 guest differs after native host rebuild")
    for offset,_,new in MOVZ:
        require(data[offset:offset+4]==bytes.fromhex(new),
                f"2GiB KTGL capacity lost at main+0x{offset:x}")
    for offset,opcode in PRESERVE:
        require(data[offset:offset+4]==bytes.fromhex(opcode),
                f"previous verified 4GiB-root, heap and align code lost +{offset:x}")

def make(source:Path,source_report:Path,repo:Path,out:Path):
    require(sys.platform=="darwin","macOS-only host build")
    require((repo/".upstream-ref").read_text().strip()==hook.ENGINE_PIN,
            "pinned NXNative identity differs")
    require(source.is_file() and source.stat().st_size==SOURCE_SIZE and
            hook.sha256(source)==SOURCE_SHA,"source IPA version/size/SHA-256 wrong")
    oldreport=json.loads(source_report.read_text())
    require(oldreport.get("project")=="Fairy2iOS" and
            oldreport.get("title_id")==TITLE and
            oldreport.get("source_run_id")==44988275455 and
            oldreport.get("from_confirmed_crash_run")==44990224107 and
            oldreport.get("repair_candidate") is True and
            oldreport.get("runtime_verified_on_iphone") is False and
            oldreport.get("metal_shader_sha256")==SHADER_SHA,
            "source report must be iPhone-crashed conservative build with original Metal")
    geometry=memory_geometry()
    ios=repo/"engine/dm/ios"
    engine=repo/"engine"
    host=engine/"dm/host"
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fairy2-global-") as temp:
        w=Path(temp);stage=w/"stage";stage.mkdir()
        hook.run(["ditto","-x","-k",source,stage])
        app=stage/"Payload/DmShell.app"
        fw=app/"Frameworks"/FRAMEWORK
        exe=fw/("DmGame"+TITLE)
        shell=app/"DmShell"
        manifest=json.loads((fw/"game.manifest.json").read_text())
        require(manifest.get("title_id","").upper()==TITLE and
                manifest.get("loader")=="FH" and
                sorted(manifest.get("modules",[]))==["main","sdk","subsdk1"],
                "source module manifest differs")
        require(exe.is_file() and shell.is_file(),"missing executable")
        metal=fw/"msl/b-0724088d3779.img"
        require(metal.is_file() and metal.stat().st_size==2640519506 and
                hook.sha256(metal)==SHADER_SHA,"original precompiled Metal lost")
        shell_sha=hook.sha256(shell)
        shmap_sha=hook.sha256(fw/"dm/shader_map.tsv")
        ent=w/"entitlements.plist"
        info=plistlib.loads((app/"Info.plist").read_bytes())
        hook.extract_entitlements(app/str(info.get("CFBundleExecutable","DmShell")),ent)
        guest_stamp=patch_main(exe,oldreport)
        src_sections=hook.otool_sections(exe)
        gen=ios/"Gen";shutil.rmtree(gen,ignore_errors=True)
        (gen/"framework/dm").mkdir(parents=True)
        (gen/"dm").mkdir(parents=True)
        flags=hook.embedded_section_assembly(exe,manifest,gen/"embed.S")
        require(len(flags)==3,"expected all three ARM64 writable sections")
        shutil.copytree(fw/"dm",gen/"framework/dm",dirs_exist_ok=True)
        shutil.copy2(fw/"game.manifest.json",gen/"framework/game.manifest.json")
        shutil.copy2(fw/"profile.tsv",gen/"framework/profile.tsv")
        profile_adjust(gen/"framework/profile.tsv",False)
        profile_adjust(fw/"profile.tsv",False)
        profile_home=Path(__file__).resolve().parents[1]/"profile"/TITLE/"game.tsv"
        require(profile_home.is_file(),"canonical profile absent")
        profiles=w/"profiles"/TITLE;profiles.mkdir(parents=True)
        shutil.copy2(profile_home,profiles/"game.tsv")
        profile_adjust(profiles/"game.tsv",True)
        fwinfo=plistlib.loads((fw/"Info.plist").read_bytes())
        env=dict(os.environ,GAME=TITLE,DM_GAME=TITLE,
                 DM_GAMES_DIR=str(profiles.parent),DM_GAMES_FIRST="1",
                 DM_BUNDLE_ID=str(fwinfo.get("CFBundleIdentifier","org.nxnative."+TITLE.lower())),
                 DM_DISPLAY_NAME=str(fwinfo.get("CFBundleDisplayName","FAIRY TAIL 2")),
                 DM_APP_VERSION=str(fwinfo.get("CFBundleShortVersionString","1.4.1")),
                 DM_TEAM_ID="0000000000",DM_SHOW_FPS="YES",MSL_SDK="iphoneos")
        p=subprocess.run([sys.executable,str(ios/"tools/gen_build.py"),str(host),str(gen)],
                         cwd=ios,env=env,text=True,capture_output=True)
        require(p.returncode==0 and "HEADER_SEARCH_PATHS =" in p.stdout,
                "iOS host generator failed: "+p.stderr[-4000:])
        head=host/"gen"/TITLE/"game_profile.h"
        h=head.read_text()
        for v in ("#define DM_GAME_MEM_RESERVE 0x140000000",
                  "#define DM_GAME_MEM_ALIAS 0x118000000",
                  "#define DM_GAME_MEM_MAP_LIMIT 1"):
            require(v.lower() in h.lower(),"native SVC compile macro missing "+v)
        ns=subprocess.run([sys.executable,str(ios/"tools/gen_objc_namespace.py"),
             "--print-tag","--game",TITLE,"--framework-name",exe.name,
             "--header",str(gen/"framework/objc_namespace.h"),
             "--exports",str(gen/"framework/exported_symbols.txt"),
             str(host),str(engine/"dm/gfx"),str(ios/"Sources"),str(ios/"framework")],
             cwd=ios,env=env,text=True,capture_output=True)
        require(ns.returncode==0,"ObjC namespace failed: "+ns.stderr[-4000:])
        tag=ns.stdout.strip()
        require(bool(re.fullmatch("[A-Za-z0-9_]+",tag)),"invalid framework namespace")
        (gen/"dm.xcconfig").write_text(p.stdout.rstrip()+"\nDM_NS_TAG = "+tag+
             "\nOTHER_LDFLAGS = $(inherited) $(DM_FRAMEWORKS) "+" ".join(flags)+"\n")
        (gen/"framework.xcconfig").write_text("OTHER_LDFLAGS = $(inherited) "+" ".join(flags)+"\n")
        (gen/"Assets.xcassets").mkdir()
        (gen/"Assets.xcassets/Contents.json").write_text('{"info":{"author":"xcode","version":1}}\n')
        hook.run(["xcodegen","generate","-q","--spec","project-framework.yml"],cwd=ios,env=env)
        products=w/"products";objects=w/"objects";products.mkdir();objects.mkdir()
        hook.run(["xcodebuild","-project",ios/"DmIOS.xcodeproj","-target","DmShellGame",
          "-configuration","Release","-sdk","iphoneos","-arch","arm64",
          "PRODUCT_NAME="+exe.name,
          "PRODUCT_BUNDLE_IDENTIFIER="+str(fwinfo.get("CFBundleIdentifier")),
          "MARKETING_VERSION="+str(fwinfo.get("CFBundleShortVersionString","1.4.1")),
          "CURRENT_PROJECT_VERSION="+str(fwinfo.get("CFBundleVersion","1")),
          "SYMROOT="+str(products),"OBJROOT="+str(objects),"DM_NS_TAG="+tag,
          "CODE_SIGNING_ALLOWED=NO","CODE_SIGNING_REQUIRED=NO","CODE_SIGN_IDENTITY=","build"],
          cwd=ios,env=env,log_file=out/"host-build.log")
        built=products/"Release-iphoneos"/FRAMEWORK/exe.name
        require(built.is_file(),"native framework not emitted by xcodebuild")
        verify_main(built,guest_stamp)
        new_sections=hook.otool_sections(built)
        with exe.open("rb") as before,built.open("rb") as after:
            for key,old in src_sections.items():
                if not (key[1].startswith("__dm") or key[0].startswith("__DM")):continue
                curr=new_sections.get(key)
                require(bool(curr) and curr["size"]==old["size"],
                        f"lost guest section {key}")
                before.seek(old["offset"]);after.seek(curr["offset"])
                left=old["size"]
                while left:
                    block=min(left,8*1024*1024)
                    require(before.read(block)==after.read(block),
                            f"guest section changed by native build: {key}")
                    left-=block
        import repack_ipa as menu
        launcher=fw/"dm/launcher.json"
        data=menu.configure_launcher(json.loads(launcher.read_text()))
        menu.validate_settings(data)
        launcher.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")
        shell_code=menu.macho_text_sha(shell)
        shutil.copy2(built,exe)
        hook.run(["xattr","-cr",fw])
        hook.run(["codesign","--force","--sign","-","--timestamp=none",fw])
        hook.run(["codesign","--verify","--strict",fw])
        hook.run(["xattr","-cr",app])
        hook.run(["codesign","--force","--sign","-","--entitlements",ent,
                  "--timestamp=none",app])
        hook.run(["codesign","--verify","--deep","--strict",app])
        verify_main(exe,guest_stamp)
        require(menu.macho_text_sha(shell)==shell_code,
                "DmShell changed in host-only rebuild")
        require(hook.sha256(metal)==SHADER_SHA and hook.sha256(fw/"dm/shader_map.tsv")==shmap_sha,
                "compiled Metal library or shader map changed")
        dest=out/OUT_NAME
        hook.run([sys.executable,engine/"dm/ios/tools/pack_ipa.py",dest,
                  "--no-reuse","Payload/DmShell.app="+str(app)],cwd=engine,env=env)
        with zipfile.ZipFile(dest) as zipped:
            prefix="Payload/DmShell.app/Frameworks/"+FRAMEWORK+"/"
            require(zipped.testzip() is None,"IPA archive CRC failure")
            runtime=zipped.read(prefix+"profile.tsv").decode()
            require("mem_alias\t0x118000000" in runtime and "mem_map_limit\t1" in runtime,
                    "global compiled runtime profile not in IPA")
            require(zipped.getinfo(prefix+"msl/b-0724088d3779.img").file_size==2640519506,
                    "compiled original shaders truncated in IPA")
            menu.validate_settings(json.loads(zipped.read(prefix+"dm/launcher.json")))
        report={"project":"Fairy2iOS","title_id":TITLE,"source_run_id":SOURCE_RUN,
                "source_sha256":SOURCE_SHA,"output_ipa":dest.name,
                "output_ipa_size_bytes":dest.stat().st_size,
                "output_ipa_sha256":hook.sha256(dest),
                "method":"Correct full KTGL child 1.25GiB to 2GiB at both guest capacity producer sites, no overlapping later allocator arena",
                "global_geometry":geometry,
                "guest_root_patch":oldreport["guest_root_patch"],
                "guest_ktgl_2g_patch":guest_stamp,
                "ktgl_virtual_region_overlap_repaired":True,
                "bin47_alias_offset":"0xc5800178",
                "device_2g_fix_verified":False,
                "host_recompiled":True,"game_shaders_recompiled":False,
                "guest_modules_rewritten":False,"shell_recompiled":False,
                "metal_shader_sha256":SHADER_SHA,"external_romfs_aoc_unchanged":True,
                "fps_selector":[30,60],"ab_swap_available":True,
                "device_boot_verified":False}
        (out/"ktgl-nooverlap-report.json").write_text(json.dumps(report,indent=2)+"\n")
        print("[Fairy2iOS GLOBAL] IPA",dest.name,"SHA-256",report["output_ipa_sha256"],
              "bytes",report["output_ipa_size_bytes"],flush=True)
        return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-ipa",required=True,type=Path)
    parser.add_argument("--source-report",required=True,type=Path)
    parser.add_argument("--repo",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    make(args.source_ipa,args.source_report,args.repo.resolve(),args.output)
