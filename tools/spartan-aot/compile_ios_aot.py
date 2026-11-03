#!/usr/bin/env python3
"""Compile generated PS4 game C and the strict ARM64 dispatcher into an iOS static archive.
The archive remains on the ephemeral runner; game-derived output is never uploaded.
"""
from pathlib import Path
import argparse, os, subprocess, hashlib, json
p=argparse.ArgumentParser()
p.add_argument("--generated",type=Path,required=True)
p.add_argument("--recomp",type=Path,required=True)
p.add_argument("--zydis",type=Path,required=True)
p.add_argument("--zycore",type=Path,required=True)
p.add_argument("--out",type=Path,required=True)
a=p.parse_args()
sdk=subprocess.check_output(["xcrun","--sdk","iphoneos","--show-sdk-path"],text=True).strip()
clang=subprocess.check_output(["xcrun","--sdk","iphoneos","--find","clang"],text=True).strip()
a.out.mkdir(parents=True,exist_ok=True)
flags=["-target","arm64-apple-ios17.4","-isysroot",sdk,"-O2","-std=gnu11","-fPIC",
       "-ffp-contract=off","-fno-strict-aliasing","-DGOW3_AOT_ONLY=1",
       "-I"+str(a.recomp/"src"),"-I"+str(a.recomp/"src/recomp"),
       "-I"+str(a.zydis/"include"),"-I"+str(a.zycore/"include")]
sources=sorted(a.generated.glob("recomp*.c"))
if not sources: raise SystemExit("No recomp*.c generated: refusing an empty AOT archive")
sources += sorted((a.recomp/"src/cpu").glob("*.c"))
sources += [a.recomp/"src/cpu/hostcall.S"]
objects=[]
for i,src in enumerate(sources):
    obj=a.out/f"{i:04d}-{src.stem}.o"
    subprocess.run([clang,*flags,"-c",str(src),"-o",str(obj)],check=True)
    objects.append(str(obj))
zydis_lib=a.zydis/"build-ios/lib/libZydis.a"
zycore_lib=a.zycore/"build-ios/lib/libZycore.a"
for lib in (zydis_lib,zycore_lib):
    if not lib.is_file(): raise SystemExit(f"Missing iOS static dependency: {lib}")
archive=a.out/"libgow3-recompiled-ios.a"
subprocess.run(["/usr/bin/libtool","-static","-o",str(archive),*objects,str(zydis_lib),str(zycore_lib)],check=True)
arch=subprocess.check_output(["xcrun","lipo","-archs",str(archive)],text=True).strip()
if arch!="arm64": raise SystemExit("AOT archive is not arm64-only: "+arch)
manifest={"architecture":arch,"target":"arm64-apple-ios17.4","generated_c_files":len(list(a.generated.glob("recomp*.c"))),
          "compiled_sources":len(sources),"archive_bytes":archive.stat().st_size,
          "archive_sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
          "strict_aot":"GOW3_AOT_ONLY=1; interpreter fallback disabled"}
(a.out/"aot-build-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
print(json.dumps(manifest,indent=2))
