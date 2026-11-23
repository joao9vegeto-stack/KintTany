#!/usr/bin/env python3
"""HookLink2iOS: settings-only repack of an already-built IPA; no shader or game build."""
from __future__ import annotations
import argparse, hashlib, json, os, plistlib, shutil, subprocess, tempfile, zipfile
from pathlib import Path, PurePosixPath

TITLE = "0400486024DEC000"
PREFIX = "Payload/DmIOS.app/"
CHUNK = 16 * 1024 * 1024
PRESETS = {
    "stable30": {"DM_FRAME_MODE":"1", "DM_DYNAMIC_RESOLUTION":"1",
                 "DM_UPSCALER":"metalfx", "DM_RT_COMP":"auto", "DM_SHOW_FPS":"1"},
    "balanced30fg": {"DM_FRAME_MODE":"2", "DM_FRAMEGEN_SCALE":"0.75",
                      "DM_DYNAMIC_RESOLUTION":"1", "DM_UPSCALER":"metalfx",
                      "DM_RT_COMP":"auto", "DM_SHOW_FPS":"1"},
    "native60": {"DM_FRAME_MODE":"0", "DM_FPS_TARGET":"60", "DM_FRAMEGEN":"0",
                 "DM_DYNAMIC_RESOLUTION":"1", "DM_UPSCALER":"metalfx",
                 "DM_RT_COMP":"auto", "DM_SHOW_FPS":"1"}
}

def fail(message):
    raise SystemExit("[HookLink2iOS repack] " + message)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(CHUNK), b""):
            h.update(part)
    return h.hexdigest()

def audit(z):
    names = z.namelist()
    if len(names) != len(set(names)):
        fail("duplicate ZIP member names")
    required = [PREFIX+"Info.plist", PREFIX+"DmIOS", PREFIX+"romfs.id"]
    if any(name not in names for name in required):
        fail("incomplete or wrong DmIOS IPA")
    marker = z.read(PREFIX+"romfs.id").decode("utf-8", "replace").strip()
    if "title="+TITLE not in marker or "version=v131072" not in marker:
        fail("wrong title/update in romfs.id")
    plist = plistlib.loads(z.read(PREFIX+"Info.plist"))
    if str(plist.get("MinimumOSVersion", "")) != "26.0":
        fail("not an iOS 26.0 IPA")
    shader_images = {x.filename:(x.file_size, x.CRC) for x in z.infolist()
                     if x.filename.startswith(PREFIX+"msl/b-") and x.filename.endswith(".img")}
    if not shader_images:
        fail("no NVN Metal image; refusing invalid thin IPA")
    if any(x.lower().endswith("romfs.img") for x in names):
        fail("RomFS unexpectedly embedded; requires external RomFS")
    return marker, shader_images

def unpack(z, root):
    seen = set()
    for info in z.infolist():
        relative = PurePosixPath(info.filename)
        if relative.is_absolute() or ".." in relative.parts or "\\" in info.filename:
            fail("path traversal: "+info.filename)
        if info.filename in seen:
            fail("duplicate member "+info.filename)
        seen.add(info.filename)
        if ((info.external_attr >> 16) & 0o170000) == 0o120000:
            fail("symlink not supported: "+info.filename)
        out = root.joinpath(*relative.parts)
        if info.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as f, out.open("wb") as dst:
            shutil.copyfileobj(f, dst, CHUNK)
        mode = (info.external_attr >> 16) & 0o777
        if mode: out.chmod(mode)

def update_env(app, changes):
    p = app/"dm"/"env.txt"
    current = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" not in line: fail("bad original env.txt line")
            key, value = line.split("=", 1)
            key = key.strip()
            if key in current or not key.startswith("DM_"):
                fail("duplicate/unexpected env key: "+key)
            current[key] = value.strip()
    # Remove mode-dependent old values, preserve all non-FPS existing flags.
    owned = set().union(*(p.keys() for p in PRESETS.values()))
    values = {key:value for key,value in current.items() if key not in owned}
    values.update(changes)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# HookLink2iOS repack; Documents/env.txt overrides this bundle file.\n" +
                 "".join(f"{key}={value}\n" for key,value in values.items()), encoding="utf-8")
    return values

def rezip(root, destination):
    with zipfile.ZipFile(destination, "w", allowZip64=True) as z:
        for path in sorted((root/"Payload").rglob("*")):
            if not path.is_file(): continue
            stored = path.suffix.lower() in (".img",".zs",".metallib",".ttf",".car",".webm")
            z.write(path, path.relative_to(root).as_posix(),
                    compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED,
                    compresslevel=None if stored else 1)

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--source", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--report", type=Path, required=True)
    a.add_argument("--preset", choices=list(PRESETS), default="balanced30fg")
    a.add_argument("--entitlements", type=Path,
                   default=Path("hooklink/Resources/presets/entitlements.plist"))
    args = a.parse_args()
    if os.uname().sysname != "Darwin" or shutil.which("codesign") is None:
        fail("macOS codesign is required; refusing unsigned changed IPA")
    if not args.entitlements.exists():
        fail("missing iOS entitlements")
    if args.source.resolve() == args.output.resolve():
        fail("never overwrite the source IPA")
    if not args.source.is_file() or args.source.stat().st_size < 20*1024*1024:
        fail("source missing or suspiciously small")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hooklink-repack-") as tmp:
        temp = Path(tmp)
        source_ipa = args.source
        with zipfile.ZipFile(args.source) as source:
            embedded = [x for x in source.infolist() if x.filename.lower().endswith(".ipa") and not x.is_dir()]
            if embedded:
                if len(embedded) != 1 or PREFIX+"DmIOS" in source.namelist():
                    fail("ambiguous source artifact")
                source_ipa = temp/"source.ipa"
                with source.open(embedded[0]) as inp, source_ipa.open("wb") as out:
                    shutil.copyfileobj(inp, out, CHUNK)
        with zipfile.ZipFile(source_ipa) as z:
            original = audit(z)
            unpack(z, temp/"package")
        app = temp/"package"/"Payload"/"DmIOS.app"
        executable = app/"DmIOS"
        executable.chmod(executable.stat().st_mode | 0o111)
        values = update_env(app, PRESETS[args.preset])
        for framework in sorted((app/"Frameworks").glob("*.framework")) if (app/"Frameworks").exists() else []:
            subprocess.run(["codesign","--force","--sign","-","--timestamp=none",str(framework)],check=True)
        subprocess.run(["codesign","--force","--sign","-","--timestamp=none",
                        "--entitlements",str(args.entitlements.resolve()),str(app)],check=True)
        subprocess.run(["codesign","--verify","--deep","--strict",str(app)],check=True)
        rezip(temp/"package", args.output)
        with zipfile.ZipFile(args.output) as zipped:
            if audit(zipped) != original:
                fail("shader library CRC/size or RomFS identity changed")
            env = zipped.read(PREFIX+"dm/env.txt").decode("utf-8")
            for key,value in PRESETS[args.preset].items():
                if f"{key}={value}\n" not in env:
                    fail("missing setting: "+key)
        report = {
          "project":"HookLink2iOS", "title_id":TITLE, "type":"settings-only-repack",
          "preset":args.preset, "settings":values,
          "source_sha256":sha256(args.source), "source_ipa_sha256":sha256(source_ipa),
          "output_name":args.output.name, "output_sha256":sha256(args.output),
          "output_size":args.output.stat().st_size,
          "shader_images_preserved":len(original[1]), "romfs_external":True,
          "engine_updated":False, "shader_recompiled":False, "game_code_recompiled":False,
          "source_engine_not_provable_from_bare_ipa":True,
          "signature":"ad-hoc; sideload installer may re-sign using player's identity",
          "note":"Documents/env.txt overrides bundle's dm/env.txt"}
        args.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,indent=2),flush=True)
        print("HOOKLINK2IOS_REPACK_OK",flush=True)

if __name__ == "__main__":
    main()
