#!/usr/bin/env python3
"""Native HookLink2iOS host relink from the *existing*, successfully built IPA.

No NUP, RomFS, shader translation, or game-code rewrite. Extracts the exact
ARM64 rewritten guest pages from the old Mach-O embedded sections and links
them with source-level X1/X2/X3 runtime backports on the pinned old shader ABI.
Only Apple's host Metal shaders (not game shaders) are regenerated.

The output is a replacement DmIOS executable. A separate, proven IPA repacker
then inserts it while preserving the game Metal image's ZIP compression/CRC.
"""
from __future__ import annotations
import argparse, hashlib, json, os, plistlib, re, shutil, struct, subprocess, sys, time, zipfile
from pathlib import Path

TITLE="0400486024DEC000"
PIN="cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
BUNDLE="Payload/DmIOS.app/"
BLOCK=16*1024*1024

def fail(msg):
    raise RuntimeError("[HookLink2iOS native relink] "+str(msg))

def cmd(argv,*,cwd=None,env=None,log=None):
    print("+", " ".join(map(str,argv)),flush=True)
    if log:
        with Path(log).open("a") as f:
            r=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
        if r.returncode:
            tail=Path(log).read_text(errors="replace")[-5000:]
            fail(f"native build exit {r.returncode}; log: {log}\n{tail}")
    else:
        subprocess.run([str(x) for x in argv],cwd=cwd,env=env,check=True)

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(BLOCK),b""):h.update(part)
    return h.hexdigest()

def extract_member(z,name,path,limit=None):
    info=z.getinfo(name)
    if limit and info.file_size>limit:fail("member too large: "+name)
    path.parent.mkdir(parents=True,exist_ok=True)
    with z.open(info) as inp,path.open("wb") as out:shutil.copyfileobj(inp,out,BLOCK)
    if path.stat().st_size!=info.file_size:fail("incomplete ZIP member: "+name)

def sections_macho(executable):
    """Read thin little-endian arm64 MH_EXECUTE LC_SEGMENT_64 section ranges."""
    secs={}
    with Path(executable).open("rb") as f:
        hdr=f.read(32)
        if len(hdr)!=32:fail("truncated Mach-O")
        magic,cpu,sub,filetype,ncmds,cmdbytes,flags,reserved=struct.unpack("<IiiIIIII",hdr)
        if magic!=0xfeedfacf or cpu!=0x0100000c or filetype!=2:
            fail(f"original binary is not thin arm64 executable ({magic:#x}, {cpu:#x}, {filetype})")
        fsize=Path(executable).stat().st_size
        end=32+cmdbytes
        if ncmds>1000 or cmdbytes>16*1024*1024 or end>fsize:fail("bad Mach-O commands")
        loc=32
        for _ in range(ncmds):
            f.seek(loc)
            desc=f.read(8)
            if len(desc)!=8:fail("truncated Mach-O command")
            command,size=struct.unpack("<II",desc)
            if size<8 or loc+size>end:fail("invalid Mach-O load command size")
            if command==0x19:
                block=desc+f.read(size-8)
                if len(block)<72:fail("truncated LC_SEGMENT_64")
                nsects=struct.unpack_from("<I",block,64)[0]
                if nsects>1000 or 72+80*nsects>len(block):fail("invalid Mach-O section table")
                for i in range(nsects):
                    sect=block[72+80*i:72+80*(i+1)]
                    name,segment,addr,nb,off,align=struct.unpack_from("<16s16sQQII",sect)
                    name=name.rstrip(b"\0").decode("ascii","replace")
                    segment=segment.rstrip(b"\0").decode("ascii","replace")
                    if not nb or off+nb>fsize:continue
                    if (segment,name) in secs:fail("duplicate Mach-O section: "+segment+","+name)
                    secs[(segment,name)]=(off,nb)
            loc+=size
    return secs

def section_sha256(executable, location):
    offset, size = location
    h=hashlib.sha256()
    with Path(executable).open("rb") as f:
        f.seek(offset)
        while size:
            part=f.read(min(size,BLOCK))
            if not part: fail("short section while verifying original guest code")
            h.update(part);size-=len(part)
    return h.hexdigest()

def assert_guest_pages_identical(original_binary,new_binary):
    old=sections_macho(original_binary)
    new=sections_macho(new_binary)
    checked={}
    for n in ("main","subsdk0","sdk"):
        keys=[("__TEXT",f"__dm{n}x0"),(f"__DM{n}W","__img"),("__TEXT",f"__dm{n}x1")]
        if ("__TEXT",f"__dm{n}x2") in old:keys.append(("__TEXT",f"__dm{n}x2"))
        for key in keys:
            if key not in old or key not in new:fail("guest segment disappeared: "+str(key))
            if old[key][1]!=new[key][1]:fail("guest section changed size: "+str(key))
            digest=section_sha256(original_binary,old[key])
            if section_sha256(new_binary,new[key])!=digest:
                fail("original guest ARM64 code/data changed during host relink: "+str(key))
            checked["/".join(key)]={"bytes":old[key][1],"sha256":digest}
    return checked

def extract_guest_sections(old_binary,ipa,z,patch_dir):
    fixups={}
    src_prefix=BUNDLE+"dm/"
    for n in ("main","subsdk0","sdk"):
        member=src_prefix+n+".fixups.tsv"
        if member not in z.namelist():fail("original IPA missing "+member)
        target=patch_dir/(n+".fixups.tsv")
        extract_member(z,member,target,16*1024*1024)
        fixups[n]={}
        for line in target.read_text(errors="replace").splitlines():
            if line.startswith("# ") and len(line.split())>=3:
                fields=line[2:].split(None,1)
                fixups[n][fields[0]]=fields[1].split()[0]
    secs=sections_macho(old_binary)
    manifest={}
    with Path(old_binary).open("rb") as f:
        for n in fixups:
            names=[("__TEXT",f"__dm{n}x0"),(f"__DM{n}W","__img"),("__TEXT",f"__dm{n}x1")]
            if ("__TEXT",f"__dm{n}x2") in secs:names.append(("__TEXT",f"__dm{n}x2"))
            if any(x not in secs for x in names):fail(f"missing original guest embedded sections for {n}: "+repr([x for x in names if x not in secs]))
            result=patch_dir/(n+".patched.bin")
            total=0; sizes=[]
            with result.open("wb") as out:
                for segment in names:
                    off,size=secs[segment]
                    f.seek(off)
                    left=size
                    while left:
                        part=f.read(min(left,BLOCK))
                        if not part:fail("short Mach-O section for "+n)
                        out.write(part);left-=len(part)
                    sizes.append(size);total+=size
            if total<0x4000 or total>1_500_000_000:fail("reconstructed guest module size suspicious: "+n)
            hdr=fixups[n]
            for req in ("TEXT_END","PATCH_OFF","KEY_PAGE_OFF","KEY_PAGE_SIZE"):
                if req not in hdr:fail("missing guest fixup header: "+n+" "+req)
            text_end=int(hdr["TEXT_END"],16)
            if sizes[0]!=(text_end+0x3fff)&~0x3fff:
                fail(f"rewritten module {n} text section differs from original fixups")
            if total%0x4000:fail("misaligned guest module "+n)
            manifest[n]={"total_bytes":total,"section_bytes":sizes,"sha256":sha256(result)}
    # Other original rewrite tables are used *unaltered* by the runtime.
    for info in z.infolist():
        if not info.filename.startswith(src_prefix) or info.is_dir():continue
        rel=info.filename[len(src_prefix):]
        if "/" in rel or not rel.endswith((".fixups.tsv",".gates.tsv",".cuts.tsv",".obs.tsv",".tsv")):continue
        target=patch_dir/rel
        if not target.exists():extract_member(z,info.filename,target,256*1024*1024)
    return manifest

def generate_and_build(engine,work,patch_dir,original_app_plist,original_binary):
    ios=engine/"dm/ios"
    gen=ios/"Gen"
    if gen.exists():shutil.rmtree(gen)
    gen.mkdir();(gen/"dm").mkdir()
    env=dict(os.environ)
    env.update(GAME=TITLE,DM_BUNDLE_ID="org.nxnative."+TITLE.lower(),
               DM_DISPLAY_NAME=str(original_app_plist.get("CFBundleDisplayName","Ocarina of Time")),
               DM_APP_VERSION=str(original_app_plist.get("CFBundleShortVersionString","1.0")),
               DM_APP_CATEGORY="public.app-category.adventure-games",DM_TEAM_ID="0000000000",
               DM_LANG=str(original_app_plist.get("DMLanguage","en-US")),DM_SHOW_FPS="YES",
               DM_SCHEME_NAME="DmIOS",GFXAPI="nvn")
    xconfig=subprocess.run([sys.executable,"tools/gen_build.py",engine/"dm/host",gen],
                            cwd=ios,env=env,capture_output=True,text=True)
    if xconfig.returncode:fail("native host generation failed: "+(xconfig.stdout+xconfig.stderr)[-4500:])
    embed=subprocess.run([sys.executable,"tools/gen_embed.py",patch_dir,gen/"embed.S","main","subsdk0","sdk"],
                         cwd=ios,env=env,capture_output=True,text=True)
    if embed.returncode:fail("embedded original guest pages failed: "+embed.stderr[-4500:])
    xconfig_text=xconfig.stdout
    if "HEADER_SEARCH_PATHS" not in xconfig_text or "DM_FRAMEWORKS" not in xconfig_text:
        fail("native host source/SDK generation is incomplete")
    outroot=(work/"XcodeDerived").resolve()
    xconfig_text+="\nOTHER_LDFLAGS = $(inherited) $(DM_FRAMEWORKS) "+embed.stdout.strip()+"\n"
    xconfig_text+="DM_XCODE_OUTPUT_ROOT = "+str(outroot)+"\n"
    (gen/"dm.xcconfig").write_text(xconfig_text,encoding="utf-8")
    # Restore original tables and the exact launcher from original IPA in Gen/dm.
    for p in (work/"original_dm").rglob("*"):
        if p.is_file():
            dest=gen/"dm"/p.relative_to(work/"original_dm")
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,dest)
    (gen/"Assets.xcassets").mkdir()
    (gen/"Assets.xcassets"/"Contents.json").write_text('{"info":{"author":"xcode","version":1}}\n')
    (gen/"Info.plist").write_bytes(plistlib.dumps(original_app_plist))
    cmd(["xcodegen","generate","-q"],cwd=ios,env=env)
    logfile=(work/"native-xcodebuild.log").resolve()
    cmd(["xcodebuild","-project","DmIOS.xcodeproj","-scheme","DmIOS","-configuration","Release",
         "-destination","generic/platform=iOS","-derivedDataPath",outroot,
         "CODE_SIGNING_ALLOWED=NO","CODE_SIGNING_REQUIRED=NO","CODE_SIGN_IDENTITY=",
         "DM_COPY_GAME_RESOURCES=NO",f"DM_XCODE_OUTPUT_ROOT={outroot}",
         f"SYMROOT={outroot}/Build/Products",f"OBJROOT={outroot}/Build/Intermediates.noindex","build"],
        cwd=ios,env=env,log=logfile)
    product=outroot/"Build/Products/Release-iphoneos/DmIOS.app/DmIOS"
    if not product.is_file() or product.stat().st_size<10*1024*1024:fail("missing/empty native host build binary")
    sec=sections_macho(product)
    for n in ("main","subsdk0","sdk"):
        if ("__TEXT",f"__dm{n}x0") not in sec:fail("new binary lost original guest code: "+n)
    checked=assert_guest_pages_identical(original_binary,product)
    target=work/"DmIOS-relinked"
    shutil.copy2(product,target)
    target.chmod(target.stat().st_mode|0o111)
    return target,logfile,checked

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",required=True,type=Path)
    ap.add_argument("--engine",required=True,type=Path)
    ap.add_argument("--work",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--report",required=True,type=Path)
    args=ap.parse_args()
    if sys.platform!="darwin":fail("Xcode/macOS runner required")
    engine=args.engine.resolve()
    if subprocess.check_output(["git","-C",str(engine),"rev-parse","HEAD"],text=True).strip()!=PIN:
        fail("wrong native engine pin")
    work=args.work.resolve()
    work.mkdir(parents=True,exist_ok=True)
    if args.source.resolve()==args.output.resolve():fail("source and output are identical")
    with zipfile.ZipFile(args.source) as z:
        names=set(z.namelist())
        for m in (BUNDLE+"Info.plist",BUNDLE+"DmIOS",BUNDLE+"romfs.id",BUNDLE+"dm/launcher.json"):
            if m not in names:fail("IPA missing "+m)
        marker=z.read(BUNDLE+"romfs.id").decode("utf-8","replace").strip()
        fields=dict(part.split("=",1) for part in marker.split()[1:] if "=" in part)
        if (fields.get("title")!=TITLE or fields.get("size")!="26247576430"
            or fields.get("index")!="b6a3def414e47ca5"):
            fail("original external RomFS identity doesn't match the working port")
        plist=plistlib.loads(z.read(BUNDLE+"Info.plist"))
        original=work/"original-DmIOS"
        extract_member(z,BUNDLE+"DmIOS",original,1_500_000_000)
        origdm=work/"original_dm"
        origdm.mkdir(parents=True,exist_ok=True)
        for info in z.infolist():
            if not info.filename.startswith(BUNDLE+"dm/") or info.is_dir():continue
            relative=info.filename[len(BUNDLE+"dm/"):]
            if ".." in Path(relative).parts or not relative or "\\" in relative:
                fail("bad original app resource path")
            extract_member(z,info.filename,origdm/relative,256*1024*1024)
        patches=work/"original_rewritten"
        patches.mkdir(exist_ok=True)
        guest=extract_guest_sections(original,args.source,z,patches)
    original_chain=(engine/"dm/gfx/nvn/dmsh_chain.h").read_bytes()
    import hooklink2ios_backport_native
    backport=hooklink2ios_backport_native.apply(engine)
    if (engine/"dm/gfx/nvn/dmsh_chain.h").read_bytes()!=original_chain:
        fail("source-level backport changed shader chain header")
    executable,buildlog,checked=generate_and_build(engine,work,patches,plist,original)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(executable,args.output)
    report={"kind":"native-host-relink","engine_base":PIN,
            "original_ipa_sha256":sha256(args.source),
            "original_executable_sha256":sha256(original),
            "new_executable_sha256":sha256(args.output),
            "original_guest_pages":guest,"guest_section_hashes_verified":checked,
            "backport_changes":backport["changes"],
            "source_level_runtime_updated":True,
            "game_code_rewritten":False,"guest_metal_shaders_recompiled":False,
            "external_romfs":True,"xcodebuild_log":str(buildlog)}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    print("HOOKLINK2IOS_NATIVE_RELINK_OK",args.output.stat().st_size,"bytes",flush=True)
if __name__=="__main__":main()
