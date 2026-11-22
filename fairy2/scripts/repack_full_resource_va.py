#!/usr/bin/env python3
"""Fairy2iOS isolated 6GiB-iOS-VA / 5GiB-global-resource fix.

The device's own game asks for 60GiB virtual address space, but a free-signed
iOS app cannot reserve even 7GiB in one mmap (pinned NXNative hle_svc.c).
Our 4GiB root is an artificial port-specific limit; after 3.33GiB of initial
KTGL regions it leaves only ~682MiB for scene resources.

The maximum known compatible native reservation is 6GiB with alias=5.375GiB
and root=5GiB; heap/stack base and per-pool physical budget stay UNCHANGED.
Five ARM64 game producers must agree. Each is a single MOVZ, so 5GiB cannot
be represented in that original four-byte slot; use five audited 12-byte
trampolines in a previously zeroed, unused padding area before rewrite gates.
All stubs preserve LR, x16, flags and the original following instruction.

The build reuses all 19,210 shaders and all guest modules except these
five constant producers and the code caves. It enables existing NXNative
diagnostics for a full resource hash and actual file opens if startup fails.
An iPhone boot remains necessary to establish whether resource creation succeeds.
"""

from __future__ import annotations
import argparse,hashlib,json,os,plistlib,re,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
import repack_host_memory as hook

TITLE="0100B9801F872000"
FRAMEWORK="DmGame"+TITLE+".framework"
SOURCE_RUN=44995690307
SOURCE_SHA="b1792f9eb522de53b2b252e3a85229584831434999edda98f31c87c7c8c256cd"
SOURCE_SIZE=1622226531
SHADER_SHA="ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b"
OUT_NAME="Fairy2iOS-FairyTail2-FullResourceVA-6GiB.ipa"
# Original main requested 60GiB; the artificial guest root cut in the
# previous IPA is exactly 4GiB at five independently audited callsites.
ROOT_SITES=((0x5f1b9c,9),(0x1d700bc,9),(0x225de0c,9),
            (0x2295a44,9),(0x2295a50,1))
PATCH_OFF=0x2c60000       # genuine AArch64 generated gate segment in NXNative
CAVE=0x2d6b000            # preferred zero padding in executable __dmmainx1
CAVE_FIRST=PATCH_OFF+0x20000
CAVE_LAST=0x2d6c000       # observed rounded end of the actual rewritten main
# x0=main original RX; W=real guest RO/data; x1=generated executable patch RX
# NEVER place a branch target in the W segment 0x22d4000..0x2c60000.
CAVE_STRIDE=16
# Two prior 2GiB child capacities and both prior heap/alignment patches.
PRESERVE=((0x21b6924,"0800a4d2"),(0x21b6954,"1900a4d2"),
          (0x2295a88,"1300a152"),(0x21b6a74,"2200a052"))
ROOT_OLD={9:bytes.fromhex("2900c0d2"),1:bytes.fromhex("2100c0d2")}
# movz xN,#1,lsl#32 then movk xN,#0x4000,lsl#16 => 0x140000000
# Exactly five GiB, NOT six; six GiB is the outer mmap reservation cap.

def branch_opcode(site:int,dest:int)->bytes:
    delta=dest-site
    require(delta%4==0 and -(128<<20)<=delta<(128<<20),
            "ARM64 branch target out of 128MiB range")
    return (0x14000000|((delta//4)&0x3ffffff)).to_bytes(4,"little")

def require(ok,message):
    if not ok: raise RuntimeError("[Fairy2iOS GLOBAL] "+message)

def memory_geometry():
    alias_base=0x328000000
    root_start=0x32c000000
    next_bin=0x3ed800000
    gpu_end=0x3d20ac000
    last_initial_region_end=0x401200000
    root_end=root_start+0x140000000
    alias_end=alias_base+0x158000000
    guest_end=0x300000000+0x180000000
    reserve=0x180000000
    alias=0x158000000
    stack=0x10000000
    initial=0x10000000
    heap=reserve-alias-stack-initial
    require(heap==0x8000000,"6GiB VA re-partition changed the 128MiB heap")
    require(root_start==alias_base+0x4000000,"root start shifted")
    require(guest_end==alias_end==0x480000000,"non-extended iOS guest AS mismatch")
    require(root_end==0x46c000000 and root_end<=alias_end,"5GiB root exceeds alias")
    require(next_bin>gpu_end,"prior 2GiB KTGL child must keep NVN out of allocator")
    require(last_initial_region_end<root_end,"guest initial regions exceed new root")
    free=root_end-last_initial_region_end
    require(free==0x6ae00000 and free>=0x60000000,
            "new root leaves less than 1.5GiB for scene resources")
    return {"guest_reserve":reserve,"guest_max_native_no_extended_va":0x180000000,
            "alias_after":alias,"heap_after":heap,"root_before":0x100000000,
            "root_after":0x140000000,"root_start":root_start,
            "root_end":root_end,"alias_base":alias_base,"alias_end":alias_end,
            "bin47_base":next_bin,"nvn_pool_end":gpu_end,
            "initial_regions_end":last_initial_region_end,
            "root_free_before_initial_regions":0x2ae00000,
            "root_free_after_initial_regions":free,
            "physical_memory_pool_unchanged":True,
            "ktgl_child_size":0x80000000,
            "bin47_alias_offset":0xc5800178,
            "no_guest_overlap":True}

def profile_adjust(path:Path,canonical:bool):
    items=path.read_text().splitlines()
    fields={x.split("\t")[0]:x.split("\t",1)[1].strip() for x in items
            if "\t" in x and not x.startswith("#")}
    require(fields.get("mem_reserve")=="0x140000000",
            "expected the known iPhone 5GiB guest source profile")
    require(fields.get("mem_alias")=="0x118000000",
            "expected prior 4.375GiB alias profile; refuse other game versions")
    out=[];found=False
    for line in items:
        key=line.partition("\t")[0]
        if key=="mem_reserve":line="mem_reserve\t0x180000000"
        elif key=="mem_alias":line="mem_alias\t0x158000000"
        elif key=="mem_map_limit":
            found=True;line="mem_map_limit\t"+("on" if canonical else "1")
        out.append(line)
    if not found:out.append("mem_map_limit\t"+("on" if canonical else "1"))
    path.write_text("\n".join(out)+"\n")

def main_sections(exe:Path):
    """Build a *logical* guest image from three different Mach-O sections.

    Pinned NXNative loader.c remaps __dmmainx0 at guest +0, __DMmainW/__img
    at guest +len(x0), and __dmmainx1 at guest +PATCH_OFF (executable).
    The virtual AArch64 offsets are not Mach-O file offsets, and a code cave
    in W would NOT be executable on iOS. Keep all three byte-identical outside
    the five branch producer sites and x1's separately checked spare bytes.
    """
    sections=hook.otool_sections(exe)
    keys={"x0":("__TEXT","__dmmainx0"),
          "w":("__DMmainW","__img"),
          "x1":("__TEXT","__dmmainx1")}
    require(all(k in sections for k in keys.values()),
            "split NXNative executable sections are missing")
    parts={}
    with exe.open("rb") as file:
        for k,sect in keys.items():
            info=sections[sect]
            require(info["size"]>0 and
                    info["offset"]+info["size"]<=exe.stat().st_size,
                    "embedded "+k+" section exceeds signed IPA framework")
            file.seek(info["offset"])
            data=file.read(info["size"])
            require(len(data)==info["size"],"truncated embedded "+k)
            parts[k]={"offset":info["offset"],"size":info["size"],"data":data}
    require(parts["x0"]["size"]>max(x[0] for x in ROOT_SITES)+4,
            "all root producers must be executable inside x0")
    require(parts["x0"]["size"]+parts["w"]["size"]==PATCH_OFF,
            "NXNative x0+W do not meet exactly at the executable x1 patch base")
    require(parts["x1"]["size"]>=0x40000 and
            (parts["x1"]["size"]&0x3fff)==0,
            "generated x1 patch area has implausible size or alignment")
    raw=parts["x0"]["data"]+parts["w"]["data"]+parts["x1"]["data"]
    require(len(raw)==PATCH_OFF+parts["x1"]["size"],
            "logical guest ARM64 offsets differ from Mach-O section layout")
    return parts,raw

def choose_cave(raw: bytes) -> int:
    """Only choose an all-zero 256B slot in the actual RX x1 patch section.

    Never use the RO/data W gap, even if it contains zero bytes, and never
    infer executability from the flattened Linux main's original padding.
    """
    needed=0x100
    boundary=min(CAVE_LAST,len(raw))
    require(boundary>=CAVE_FIRST+needed,
            f"genuine x1 executable patch section too short: {len(raw):#x}")
    # Prefer known padding near the true end, then search last to first.
    options=[CAVE]+list(range((boundary-needed)&~0xfff,CAVE_FIRST-1,-0x1000))
    for off in options:
        if (off&0xf)==0 and CAVE_FIRST<=off and off+needed<=boundary and raw[off:off+needed]==bytes(needed):
            return off
    sample=[(hex(p),raw[p:p+16].hex()) for p in options[:9]]
    raise RuntimeError("[Fairy2iOS GLOBAL] no original zero-code region in executable __dmmainx1; refusing to touch writable W or active gates: "+repr(sample))

def patch_bytes(raw:bytes)->tuple[bytes,dict]:
    cave_base=choose_cave(raw)
    patched=bytearray(raw)
    stubs=[]
    for i,(site,reg) in enumerate(ROOT_SITES):
        old=ROOT_OLD[reg]
        require(raw[site:site+4]==old,
                f"source not 4GiB at independently audited site main+0x{site:x}")
        cave=cave_base+i*CAVE_STRIDE
        first=(0xd2c00020|reg).to_bytes(4,"little")
        second=(0xf2a80000|reg).to_bytes(4,"little")
        forward=branch_opcode(site,cave)
        backward=branch_opcode(cave+8,site+4)
        patched[site:site+4]=forward
        patched[cave:cave+12]=first+second+backward
        stubs.append({"site":f"main+0x{site:x}","target":f"main+0x{cave:x}",
                      "destination_register":f"x{reg}",
                      "5g_constant_hex":"0x140000000",
                      "back_to":f"main+0x{site+4:x}"})
    for site,opcode in PRESERVE:
        require(raw[site:site+4]==bytes.fromhex(opcode),
                f"prior 2GiB KTGL, heap or alignment opcode lost main+0x{site:x}")
        require(patched[site:site+4]==bytes.fromhex(opcode),
                f"unexpected mutation of existing relevant patch at {site:x}")
    differences=sum(a!=b for a,b in zip(raw,patched))
    require(5*4 <= differences <= 5*16 and
            patched[cave_base+len(ROOT_SITES)*CAVE_STRIDE:cave_base+0x100] ==
            raw[cave_base+len(ROOT_SITES)*CAVE_STRIDE:cave_base+0x100],
            "modified more than five ARM64 producers and five stubs")
    return bytes(patched),{"old_root":0x100000000,"new_root":0x140000000,
                           "trampoline_count":len(stubs),"trampoline_stride":CAVE_STRIDE,
                           "instructions_added":3*len(stubs),
                           "sites":stubs,"actual_modified_bytes":differences,
                           "code_cave":f"main+0x{cave_base:x}",
                           "old_cave_all_zeros":True}

def patch_main(exe:Path,src_report:dict):
    parts,raw=main_sections(exe)
    source=(src_report.get("guest_ktgl_2g_patch") or {})
    expected=source.get("after_sha256")
    require(bool(expected) and
            hashlib.sha256(parts["x0"]["data"]).hexdigest()==expected,
            "source 2GiB IPA's exact original x0 shader-free guest SHA differs")
    fixed,proof=patch_bytes(raw)
    require(fixed[parts["x0"]["size"]:PATCH_OFF]==raw[parts["x0"]["size"]:PATCH_OFF],
            "NEVER change the guest W/RO/data segment")
    checks={}
    with exe.open("r+b") as file:
        for label,offset in (("x0",0),("x1",PATCH_OFF)):
            item=parts[label]
            segment=fixed[offset:offset+item["size"]]
            require(len(segment)==item["size"],
                    "patched "+label+" shortened")
            file.seek(item["offset"])
            require(file.read(item["size"])==item["data"],
                    "framework changed after guest sections audit")
            file.seek(item["offset"])
            file.write(segment)
            checks[label+"_before_sha256"]=hashlib.sha256(item["data"]).hexdigest()
            checks[label+"_after_sha256"]=hashlib.sha256(segment).hexdigest()
    checks["w_sha256"]=hashlib.sha256(parts["w"]["data"]).hexdigest()
    checks["x0_size"]=parts["x0"]["size"]
    checks["w_size"]=parts["w"]["size"]
    checks["x1_size"]=parts["x1"]["size"]
    return {"before_sha256":hashlib.sha256(raw).hexdigest(),
            "after_sha256":hashlib.sha256(fixed).hexdigest(),**checks,**proof}

def verify_main(exe:Path,stamp:dict):
    parts,raw=main_sections(exe)
    require(hashlib.sha256(raw).hexdigest()==stamp["after_sha256"],
            "after host-only iOS compile, flattened guest main code differs")
    for key in ("x0","x1"):
        require(hashlib.sha256(parts[key]["data"]).hexdigest()==stamp[key+"_after_sha256"],
                "relinked guest executable "+key+" differs")
    require(hashlib.sha256(parts["w"]["data"]).hexdigest()==stamp["w_sha256"],
            "native compiler unexpectedly changed guest W/RO/data")
    cave_base=int(stamp["code_cave"].split("+0x",1)[1],16)
    require(CAVE_FIRST<=cave_base and cave_base+0x100<=min(CAVE_LAST,len(raw)),
            "code cave is not in executable guest x1")
    for i,(site,reg) in enumerate(ROOT_SITES):
        cave=cave_base+i*CAVE_STRIDE
        require(raw[site:site+4]==branch_opcode(site,cave),
                f"guest original-code producer main+0x{site:x} B lost")
        want=(0xd2c00020|reg).to_bytes(4,"little") + (0xf2a80000|reg).to_bytes(4,"little") + branch_opcode(cave+8,site+4)
        require(raw[cave:cave+12]==want,
                "guest executable x1 trampoline does not build exact 5GiB")
    for site,opcode in PRESERVE:
        require(raw[site:site+4]==bytes.fromhex(opcode),
                f"old 2GiB KTGL child, 128MiB heap or alignment patch lost: {site:x}")

def make(source:Path,source_report:Path,repo:Path,out:Path):
    require(sys.platform=="darwin","macOS-only host build")
    require((repo/".upstream-ref").read_text().strip()==hook.ENGINE_PIN,
            "pinned NXNative identity differs")
    require(source.is_file() and source.stat().st_size==SOURCE_SIZE and
            hook.sha256(source)==SOURCE_SHA,"source IPA version/size/SHA-256 wrong")
    oldreport=json.loads(source_report.read_text())
    require(oldreport.get("project")=="Fairy2iOS" and
            oldreport.get("title_id")==TITLE and
            oldreport.get("source_run_id")==44992666178 and
            (oldreport.get("guest_ktgl_2g_patch") or {}).get("new_region_bytes")==0x80000000 and
            (oldreport.get("guest_ktgl_2g_patch") or {}).get("instructions_changed")==2 and
            oldreport.get("device_boot_verified") is False and
            oldreport.get("metal_shader_sha256")==SHADER_SHA,
            "source report must be device-tested 2GiB KTGL candidate with original shaders")
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
        for v in ("#define DM_GAME_MEM_RESERVE 0x180000000",
                  "#define DM_GAME_MEM_ALIAS 0x158000000",
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
        data["settings"]=[r for r in data["settings"]
                          if r.get("env") not in ("DM_FS","DM_CRASH_PEEK")]
        data["settings"].extend([
            {"env":"DM_FS","kind":"toggle","section":"Diagnostics",
             "label":"Rastrear abertura de recursos (RDB/FS)",
             "note":"Mostra os arquivos que o jogo realmente tenta abrir antes do erro.",
             "default":"1","on":"1","off":"0","level":"advanced"},
            {"env":"DM_CRASH_PEEK","kind":"choice","section":"Diagnostics",
             "label":"Registro completo da mensagem do recurso",
             "note":"No crash, despeja 256 bytes de x1; inclui Hash[0x...] completo.",
             "default":"x1","options":[["x1","Registrar mensagem e hash do recurso"]],
             "level":"advanced"}])
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
            require("mem_reserve\t0x180000000" in runtime and "mem_alias\t0x158000000" in runtime and "mem_map_limit\t1" in runtime,
                    "global compiled runtime profile not in IPA")
            require(zipped.getinfo(prefix+"msl/b-0724088d3779.img").file_size==2640519506,
                    "compiled original shaders truncated in IPA")
            menu.validate_settings(json.loads(zipped.read(prefix+"dm/launcher.json")))
        report={"project":"Fairy2iOS","title_id":TITLE,"source_run_id":SOURCE_RUN,
                "source_sha256":SOURCE_SHA,"output_ipa":dest.name,
                "output_ipa_size_bytes":dest.stat().st_size,
                "output_ipa_sha256":hook.sha256(dest),
                "method":"iOS 6GiB MAX single mmap; preserve 128MiB heap/256MiB stack, expand alias 4.375 to 5.375GiB and root 4 to 5GiB using five precise ARM64 trampolines; retain KTGL 2GiB region",
                "global_geometry":geometry,
                "guest_root_patch":oldreport["guest_root_patch"],
                "guest_ktgl_2g_patch":oldreport["guest_ktgl_2g_patch"],
                "guest_root_5g_patch":guest_stamp,
                "ktgl_virtual_region_overlap_repaired":True,
                "bin47_alias_offset":"0xc5800178",
                "runtime_resource_hash_trace":True,
                "runtime_fs_trace":True,
                "device_root_5g_fix_verified":False,
                "host_recompiled":True,"game_shaders_recompiled":False,
                "guest_modules_rewritten":False,"shell_recompiled":False,
                "metal_shader_sha256":SHADER_SHA,"external_romfs_aoc_unchanged":True,
                "fps_selector":[30,60],"ab_swap_available":True,
                "device_boot_verified":False}
        (out/"full-resource-va-report.json").write_text(json.dumps(report,indent=2)+"\n")
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
