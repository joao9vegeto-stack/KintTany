#!/usr/bin/env python3
"""Fairy Tail 2: HookLink-style selective rebuild of the native host only.

Rebuilds only the per-game iOS host binary using original IPA embedded ARM64
modules verbatim. Reuses all existing game shaders and the unchanged DmShell.
Does not use Colab, game packages, NXNative rewrite, dmsh_build.py, or Metal
game shader compilation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

TITLE_ID = "0100B9801F872000"
FRAMEWORK_NAME = f"DmGame{TITLE_ID}.framework"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"
SOURCE_RUN_ID = 44965722551
SOURCE_IPA_SIZE = 1622225666
SOURCE_IPA_SHA256 = "b390754af72fc8b6c00bd54bd5d5d5dbbeb393d77b9aa1292d288e0131fabcf9"
# Start with an iPhone-safe 5GiB block; reclaim 896MiB of address space from
# the over-large alias reservation to expand the guest heap region 128MiB -> 1GiB.
MEM_RESERVE = 0x140000000
OLD_ALIAS = 0x118000000
NEW_ALIAS = 0xE0000000
OLD_HEAP_CAP = MEM_RESERVE - OLD_ALIAS - 0x10000000 - 0x10000000
NEW_HEAP_CAP = MEM_RESERVE - NEW_ALIAS - 0x10000000 - 0x10000000


def fail(message: str) -> None:
    raise SystemExit("[Fairy2iOS selective host repack] ERROR: " + message)


def log(message: str) -> None:
    print("[Fairy2iOS selective host repack] " + message, flush=True)


def run(command, *, cwd: Path | None = None, env=None, capture=False, log_file: Path | None = None):
    command = [str(x) for x in command]
    log("+ " + " ".join(command))
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("w", encoding="utf-8") as out:
            p = subprocess.run(command, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, text=True)
        if p.returncode:
            tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
            fail(f"command failed ({p.returncode}): {' '.join(command)}\n" + "\n".join(tail))
        return p
    p = subprocess.run(command, cwd=cwd, env=env, text=True,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None)
    if p.returncode:
        detail = ((p.stdout or "") + "\n" + (p.stderr or ""))[-12000:]
        fail(f"command failed ({p.returncode}): {' '.join(command)}\n{detail}")
    return p


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def copy_zip_member(z: zipfile.ZipFile, info: zipfile.ZipInfo, dest: Path) -> None:
    rel = PurePosixPath(info.filename)
    if rel.is_absolute() or ".." in rel.parts:
        fail("unsafe artifact member: " + info.filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with z.open(info) as src, dest.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=16 * 1024 * 1024)


def otool_sections(binary: Path) -> dict[tuple[str, str], dict[str, int]]:
    out = run(["otool", "-l", binary], capture=True).stdout
    lines = out.splitlines()
    found: dict[tuple[str, str], dict[str, int]] = {}
    i = 0
    while i < len(lines):
        if lines[i].strip() != "Section":
            i += 1
            continue
        block = []
        i += 1
        while i < len(lines) and lines[i].strip() not in ("Section",) and not re.match(r"^\s*Load command \d+", lines[i]):
            block.append(lines[i])
            i += 1
        values = {}
        for line in block:
            bits = line.split()
            if len(bits) >= 2 and bits[0] in {"sectname", "segname", "addr", "size", "offset"}:
                values[bits[0]] = bits[1]
        if "sectname" in values and "segname" in values and "size" in values and "offset" in values:
            try:
                found[(values["segname"], values["sectname"])] = {
                    "offset": int(values["offset"], 0),
                    "size": int(values["size"], 0),
                }
            except ValueError:
                fail(f"otool returned invalid section coordinates: {values}")
    return found


def embedded_section_assembly(binary: Path, manifest: dict, output: Path) -> list[str]:
    sections = otool_sections(binary)
    modules = manifest.get("modules")
    if not isinstance(modules, list) or not modules:
        fail("game.manifest.json has no module list")
    required: list[tuple[str, str, bool]] = []
    for module in modules:
        if not isinstance(module, str) or not re.fullmatch(r"[A-Za-z0-9]+", module):
            fail(f"invalid module name in manifest: {module!r}")
        required += [
            ("__TEXT", f"__dm{module}x0", True),
            (f"__DM{module}W", "__img", True),
            ("__TEXT", f"__dm{module}x1", True),
            ("__TEXT", f"__dm{module}x2", False),
        ]
    if int(manifest.get("nro_count", 0) or 0) > 0:
        required += [
            ("__TEXT", "__dm_nro_x0", True),
            ("__DM_NRO_W", "__img", True),
            ("__TEXT", "__dm_nro_x1", True),
            ("__DATA", "__dm_nro_tab", True),
        ]
    jit = ("__TEXT", "__dm_jit")
    if jit in sections:
        required.append((jit[0], jit[1], True))

    selected = []
    for seg, sect, mandatory in required:
        entry = sections.get((seg, sect))
        if entry is None or entry["size"] <= 0:
            if mandatory:
                fail(f"source framework lacks embedded module section {seg},{sect}")
            continue
        if entry["offset"] < 0 or entry["offset"] + entry["size"] > binary.stat().st_size:
            fail(f"embedded section {seg},{sect} runs past the source framework binary")
        if (seg, sect) != ("__DATA", "__dm_nro_tab") and entry["size"] % 0x4000:
            fail(f"embedded code section {seg},{sect} is not 16 KiB aligned")
        selected.append((seg, sect, entry["offset"], entry["size"]))

    output.parent.mkdir(parents=True, exist_ok=True)
    quoted = str(binary.resolve()).replace("\\", "\\\\").replace('"', '\\"')
    lines = ["// Extracted from the installed IPA; guest module bytes are not rebuilt."]
    for seg, sect, offset, size in selected:
        lines += [f".section {seg},{sect}"]
        lines += [".p2align 3" if (seg, sect) == ("__DATA", "__dm_nro_tab") else ".p2align 14"]
        lines += [f'.incbin "{quoted}", 0x{offset:x}, 0x{size:x}']
        if (seg, sect) != ("__DATA", "__dm_nro_tab"):
            lines.append(".p2align 14")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rw_segments = sorted({seg for seg, sect, _, _ in selected if seg.startswith("__DM") and sect == "__img"})
    return [f"-Wl,-segprot,{seg},rw,rw" for seg in rw_segments]


def extract_entitlements(executable: Path, output: Path) -> dict:
    p = subprocess.run(["codesign", "-d", "--entitlements", ":-", executable],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    raw = p.stdout + "\n" + p.stderr
    start, end = raw.find("<?xml"), raw.rfind("</plist>")
    if p.returncode != 0 or start < 0 or end < 0:
        fail("could not extract the existing app entitlements; refusing to lose the Increased Memory Limit capability")
    xml = raw[start:end + len("</plist>")]
    try:
        ent = plistlib.loads(xml.encode("utf-8"))
    except Exception as e:
        fail(f"the source app entitlements are not valid plist XML: {e}")
    if ent.get("com.apple.developer.kernel.increased-memory-limit") is not True:
        fail("source IPA does not carry Increased Memory Limit; refusing to package a lower-memory replacement")
    output.write_bytes(plistlib.dumps(ent, fmt=plistlib.FMT_XML, sort_keys=False))
    return ent



import tempfile


def profile_row(path: Path, key: str) -> str:
    rows=[line.partition("\t")[2] for line in path.read_text().splitlines()
          if line.split("\t",1)[0]==key]
    if len(rows)!=1: fail(f"expected one profile row {key}, got {len(rows)}: {path}")
    return rows[0].strip()

def change_profile(path: Path):
    lines=path.read_text().splitlines()
    if profile_row(path,"mem_reserve").lower()!=hex(MEM_RESERVE):
        fail("source memory block is not the measured 5 GiB layout")
    if profile_row(path,"mem_alias").lower()!=hex(OLD_ALIAS):
        fail("unexpected source alias layout: refusing blind correction")
    changed=[]
    for line in lines:
        if line.startswith("mem_alias\t"):
            changed.append("mem_alias\t"+hex(NEW_ALIAS))
        else:
            changed.append(line)
    path.write_text("\n".join(changed)+"\n")
    if profile_row(path,"mem_alias")!=hex(NEW_ALIAS):
        fail("new alias value did not persist")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-ipa",type=Path,required=True)
    ap.add_argument("--source-report",type=Path,required=True)
    ap.add_argument("--nx2apple-root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if sys.platform!="darwin": fail("requires an Apple Silicon macOS runner")
    nx=args.nx2apple_root.resolve()
    if (nx/".upstream-ref").read_text().strip()!=ENGINE_PIN:
        fail("NXNative engine pin mismatch")
    ios=nx/"engine/dm/ios"
    host=nx/"engine/dm/host"
    engine=nx/"engine"
    for p in [ios/"project-framework.yml",ios/"tools/gen_build.py",engine/"dm/ios/tools/pack_ipa.py"]:
        if not p.is_file():fail(f"missing modern Route-C framework source: {p}")
    original=args.source_ipa.resolve()
    if original.stat().st_size!=SOURCE_IPA_SIZE or sha256(original)!=SOURCE_IPA_SHA256:
        fail("original Fairy Tail 2 IPA length/SHA-256 mismatch")
    old_report=json.loads(args.source_report.read_text())
    if old_report.get("project")!="Fairy2iOS" or old_report.get("title_id")!=TITLE_ID:
        fail("original build report is not Fairy Tail 2")
    original_shader=old_report.get("shader_payload") or {}
    if original_shader.get("size_bytes")!=2640519506 or not re.fullmatch(r"[0-9a-f]{64}",original_shader.get("sha256","")):
        fail("source 2.64 GB compiled Metal image identity mismatch")
    if NEW_HEAP_CAP!=0x40000000 or OLD_HEAP_CAP!=0x08000000:
        fail("heap cap arithmetic mismatch")
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fairy2-host-repack-") as temp:
        work=Path(temp)
        stage=work/"stage";stage.mkdir()
        log("Original source verified; extracting only the existing completed IPA")
        run(["ditto","-x","-k",original,stage])
        app=stage/"Payload/DmShell.app"
        fw=app/"Frameworks"/FRAMEWORK_NAME
        old_binary=fw/FRAMEWORK_NAME.removesuffix(".framework")
        manifest_file=fw/"game.manifest.json"
        if not old_binary.is_file() or not manifest_file.is_file():fail("source framework absent")
        manifest=json.loads(manifest_file.read_text())
        if manifest.get("title_id","").upper()!=TITLE_ID or manifest.get("framework")!=FRAMEWORK_NAME:
            fail("original manifest identity mismatch")
        if manifest.get("loader")!="FH" or sorted(manifest.get("modules",[]))!=["main","sdk","subsdk1"]:
            fail("source is not the expected FH Route-C framework with main/subsdk1/sdk")
        profile=fw/"profile.tsv"
        old_alias=profile_row(profile,"mem_alias")
        old_reserve=profile_row(profile,"mem_reserve")
        if old_alias.lower()!=hex(OLD_ALIAS) or old_reserve.lower()!=hex(MEM_RESERVE):
            fail("source profile has a different memory layout")
        executable=plistlib.loads((fw/"Info.plist").read_bytes()).get("CFBundleExecutable")
        if executable!=old_binary.name:fail("source framework executable mismatch")
        old_info=plistlib.loads((app/"Info.plist").read_bytes())
        entitlements=work/"DmShell.entitlements"
        extract_entitlements(app/str(old_info.get("CFBundleExecutable","DmShell")),entitlements)
        old_sections=otool_sections(old_binary)
        old_shader=fw/"msl/b-0724088d3779.img"
        if not old_shader.is_file() or old_shader.stat().st_size!=2640519506:
            fail("original compiled Metal shader image missing")
        old_shader_sha=sha256(old_shader)
        if old_shader_sha!=original_shader["sha256"]:
            fail("original compiled shader SHA-256 differs from first-run report")

        gen=ios/"Gen"
        shutil.rmtree(gen,ignore_errors=True)
        (gen/"dm").mkdir(parents=True)
        (gen/"framework/dm").mkdir(parents=True)
        embed=gen/"embed.S"
        segment_flags=embedded_section_assembly(old_binary,manifest,embed)
        if len(segment_flags)!=3:
            fail("expected three embedded writable NSO module segments")
        shutil.copytree(fw/"dm",gen/"framework/dm",dirs_exist_ok=True)
        shutil.copy2(manifest_file,gen/"framework/game.manifest.json")
        shutil.copy2(profile,gen/"framework/profile.tsv")
        change_profile(gen/"framework/profile.tsv")
        change_profile(profile)

        # The host gets its compile-time game_profile.h from a per-run overlay.
        # Editing the framework's profile.tsv alone would not change memory macros.
        # Runtime profile.tsv is a serialized numeric representation, e.g.
        # present_interval=0. game.py/header() requires the surveyed game.tsv
        # source with textual enums (game/display). HookLink keeps that
        # distinction as well. Never feed runtime profile.tsv to gen_build.py.
        canonical=Path(__file__).resolve().parents[1]/"profile"/TITLE_ID/"game.tsv"
        if not canonical.is_file():
            fail("Missing canonical game.tsv recovered from Colab preparation")
        if profile_row(canonical,"mem_alias").lower()!=hex(OLD_ALIAS):
            fail("Canonical survey profile drift")
        overlay=work/"profiles"/TITLE_ID
        overlay.mkdir(parents=True)
        shutil.copy2(canonical,overlay/"game.tsv")
        change_profile(overlay/"game.tsv")
        fw_info=plistlib.loads((fw/"Info.plist").read_bytes())
        env=os.environ.copy()
        env.update({
           "GAME":TITLE_ID,"DM_GAME":TITLE_ID,
           "DM_GAMES_DIR":str(work/"profiles"),"DM_GAMES_FIRST":"1",
           "DM_BUNDLE_ID":str(fw_info.get("CFBundleIdentifier","org.nxnative."+TITLE_ID.lower())),
           "DM_DISPLAY_NAME":str(fw_info.get("CFBundleDisplayName","FAIRY TAIL 2")),
           "DM_APP_VERSION":str(fw_info.get("CFBundleShortVersionString","1.4.1")),
           "DM_TEAM_ID":"0000000000",
           "DM_SHOW_FPS":"YES",
           "DM_LANG":str(old_info.get("DMLanguage","en-GB")),
           "MSL_SDK":"iphoneos",
        })
        log("Rebuilding native host only: heap cap 128 MiB -> 1 GiB, alias 4.375 GiB -> 3.5 GiB")
        conf=subprocess.run([sys.executable,str(ios/"tools/gen_build.py"),str(host),str(gen)],
                            cwd=ios,env=env,text=True,capture_output=True)
        if conf.returncode:fail("gen_build.py failed:\n"+conf.stdout[-8000:]+"\n"+conf.stderr[-10000:])
        if "HEADER_SEARCH_PATHS =" not in conf.stdout or "OTHER_CFLAGS =" not in conf.stdout:
            fail("gen_build.py missed mandatory iOS host compile flags")
        header=host/"gen"/TITLE_ID/"game_profile.h"
        if not header.is_file():fail("iOS native host game_profile.h not generated")
        headers=header.read_text()
        required=[
          "#define DM_GAME_MEM_ALIAS "+hex(NEW_ALIAS),
          "#define DM_GAME_MEM_RESERVE "+hex(MEM_RESERVE),
        ]
        for macro in required:
            if macro.lower() not in headers.lower():
                fail(f"generated host profile did not include target macro {macro}")
        (gen/"dm.xcconfig").write_text(conf.stdout.rstrip()+"\nOTHER_LDFLAGS = $(inherited) $(DM_FRAMEWORKS) "+" ".join(segment_flags)+"\n")
        (gen/"framework.xcconfig").write_text("OTHER_LDFLAGS = $(inherited) "+" ".join(segment_flags)+"\n")
        (gen/"Assets.xcassets").mkdir()
        (gen/"Assets.xcassets/Contents.json").write_text(json.dumps({"info":{"author":"xcode","version":1}})+"\n")

        run(["xcodegen","generate","-q","--spec","project-framework.yml"],cwd=ios,env=env)
        products=work/"products";objects=work/"objects"
        products.mkdir();objects.mkdir()
        log("Xcode: ONLY DmShellGame native host framework, not shaders/game modules/Shell")
        run([
           "xcodebuild","-project",ios/"DmIOS.xcodeproj",
           "-target","DmShellGame","-configuration","Release",
           "-sdk","iphoneos","-arch","arm64",
           "PRODUCT_NAME="+old_binary.name,
           "PRODUCT_BUNDLE_IDENTIFIER="+str(fw_info.get("CFBundleIdentifier","org.nxnative."+TITLE_ID.lower())),
           "MARKETING_VERSION="+str(fw_info.get("CFBundleShortVersionString","1.4.1")),
           "CURRENT_PROJECT_VERSION="+str(fw_info.get("CFBundleVersion","1")),
           "SYMROOT="+str(products),"OBJROOT="+str(objects),
           "CODE_SIGNING_ALLOWED=NO","CODE_SIGNING_REQUIRED=NO","CODE_SIGN_IDENTITY=","build"
        ],cwd=ios,env=env,log_file=output/"host-build.log")
        built=products/"Release-iphoneos"/FRAMEWORK_NAME/old_binary.name
        if not built.is_file():
            candidates=list((products/"Release-iphoneos").glob("*.framework/"+old_binary.name))
            if len(candidates)!=1:fail("host-only Xcode did not emit the expected framework executable")
            built=candidates[0]
        new_secs=otool_sections(built)
        for section in old_sections:
            if section[1].startswith("__dm") or section[0].startswith("__DM"):
                if section not in new_secs:fail(f"lost embedded guest section {section}")
                if new_secs[section]["size"]!=old_sections[section]["size"]:
                    fail(f"guest module bytes changed size in native-host-only rebuild: {section}")
        old_asm=embedded_section_assembly(old_binary,manifest,work/"verify-old.S")
        new_asm=embedded_section_assembly(built,manifest,work/"verify-new.S")
        if old_asm!=new_asm:fail("embedded segment protection inventory changed")
        # Compare every embedded guest section byte for byte, not just sizes.
        with old_binary.open("rb") as a, built.open("rb") as b:
            for k,v in old_sections.items():
                if not (k[1].startswith("__dm") or k[0].startswith("__DM")):
                    continue
                nb=new_secs[k]
                a.seek(v["offset"]);b.seek(nb["offset"])
                todo=v["size"]
                while todo:
                    n=min(todo,8*1024*1024)
                    if a.read(n)!=b.read(n):fail(f"rewritten ARM64 game code changed: {k}")
                    todo-=n

        # Existing 30/60 FPS and A/B control UI is retained, plus memory SVC
        # telemetry; the Shell executable itself is copied exactly.
        import importlib.util
        helper_path=Path(__file__).resolve().parent/"repack_ipa.py"
        spec=importlib.util.spec_from_file_location("fairy2_menu",helper_path)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        launcher=fw/"dm/launcher.json"
        settings=mod.configure_launcher(json.loads(launcher.read_text()))
        mod.validate_settings(settings)
        launcher.write_text(json.dumps(settings,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        original_shell_hash=sha256(app/"DmShell")
        log("Reinserting new host binary into original framework; Metal and Shell unchanged")
        shutil.copy2(built,old_binary)
        run(["xattr","-cr",fw])
        run(["codesign","--force","--sign","-","--timestamp=none",fw])
        run(["codesign","--verify","--strict",fw])
        run(["xattr","-cr",app])
        run(["codesign","--force","--sign","-","--entitlements",entitlements,
             "--timestamp=none",app])
        run(["codesign","--verify","--deep","--strict",app])
        if sha256(app/"DmShell")!=original_shell_hash:
            fail("Shell Mach-O unexpectedly changed")
        if sha256(old_shader)!=old_shader_sha:
            fail("reused Metal shader library changed in selective host rebuild")
        output_ipa=output/"Fairy2iOS-FairyTail2-host-memory-repack.ipa"
        run([sys.executable,engine/"dm/ios/tools/pack_ipa.py",output_ipa,
             "--no-reuse","Payload/DmShell.app="+str(app)],cwd=engine,env=env)
        with zipfile.ZipFile(output_ipa) as z:
            path="Payload/DmShell.app/Frameworks/"+FRAMEWORK_NAME+"/"
            required=["Payload/DmShell.app/DmShell",path+old_binary.name,
                      path+"profile.tsv",path+"game.manifest.json",
                      path+"msl/b-0724088d3779.img",path+"dm/launcher.json"]
            if any(n not in z.namelist() for n in required):
                fail("repacked IPA missing essential framework or compiled shader")
            if z.getinfo(path+"msl/b-0724088d3779.img").file_size!=2640519506:
                fail("repacked IPA truncated the original shaders")
            p=z.read(path+"profile.tsv").decode()
            if "mem_alias\t"+hex(NEW_ALIAS) not in p or "mem_reserve\t"+hex(MEM_RESERVE) not in p:
                fail("new compiled memory profile not present in IPA")
            cfg=json.loads(z.read(path+"dm/launcher.json"))
            mod.validate_settings(cfg)
            if z.testzip() is not None:fail("IPA internal ZIP CRC corrupt")
        result={
            "project":"Fairy2iOS","source_run_id":SOURCE_RUN_ID,
            "source_ipa_sha256":SOURCE_IPA_SHA256,
            "output_ipa":output_ipa.name,"output_sha256":sha256(output_ipa),
            "output_size_bytes":output_ipa.stat().st_size,
            "method":"HookLink2iOS framework-host-only rebuild around unchanged embedded guest modules",
            "host_recompiled":True,"guest_modules_rewritten":False,
            "game_shaders_recompiled":False,"shared_shell_recompiled":False,
            "metal_shader_sha256":old_shader_sha,
            "mem_reserve":hex(MEM_RESERVE),"old_mem_alias":hex(OLD_ALIAS),
            "new_mem_alias":hex(NEW_ALIAS),
            "heap_region_before_bytes":OLD_HEAP_CAP,"heap_region_after_bytes":NEW_HEAP_CAP,
            "settings":{"DM_FPS_TARGET":[30,60],"DM_PAD_MAP":"A=B,B=A","DM_SVC":"1"},
            "crash_root_cause_verified":False,
            "runtime_boot_fix_verified_on_iphone":False,
            "external_romfs_aoc_unchanged":True
        }
        (output/"host-repack-report.json").write_text(json.dumps(result,indent=2)+"\n")
        log("Framework-only host repack completed: "+json.dumps({k:result[k] for k in
             ("output_ipa","output_sha256","heap_region_after_bytes","game_shaders_recompiled")}))
if __name__=="__main__":
    main()
