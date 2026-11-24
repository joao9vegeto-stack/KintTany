#!/usr/bin/env python3
"""HookLink2iOS: settings-only repack of an already-built IPA; no shader or game build."""
from __future__ import annotations
import argparse, hashlib, json, os, plistlib, shutil, subprocess, tempfile, zipfile, re
from pathlib import Path, PurePosixPath
from decimal import Decimal, InvalidOperation, localcontext

TITLE = "0400486024DEC000"
PREFIX = "Payload/DmIOS.app/"
CHUNK = 16 * 1024 * 1024
PRESETS = {
    "stable30": {"DM_FRAME_MODE":"1", "DM_FPS_TARGET":"30", "DM_FRAMEGEN":"0", "DM_DYNAMIC_RESOLUTION":"1",
                 "DM_UPSCALER":"metalfx", "DM_RT_COMP":"auto", "DM_SHOW_FPS":"1",
                 "DM_HOOKLINK_X3_CHAIN":"0", "DM_NVN_WS_MB":"4800"},
    "balanced30fg": {"DM_FRAME_MODE":"2", "DM_FPS_TARGET":"30", "DM_FRAMEGEN":"1", "DM_FRAMEGEN_SCALE":"0.75",
                      "DM_DYNAMIC_RESOLUTION":"1", "DM_UPSCALER":"metalfx",
                      "DM_RT_COMP":"auto", "DM_SHOW_FPS":"1",
                 "DM_HOOKLINK_X3_CHAIN":"0", "DM_NVN_WS_MB":"4800"},
    "native60": {"DM_FRAME_MODE":"0", "DM_FPS_TARGET":"60", "DM_FRAMEGEN":"0",
                 "DM_DYNAMIC_RESOLUTION":"1", "DM_UPSCALER":"metalfx",
                 "DM_RT_COMP":"auto", "DM_SHOW_FPS":"1",
                 "DM_HOOKLINK_X3_CHAIN":"0", "DM_NVN_WS_MB":"4800"}
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
    parts = marker.split()
    fields = dict(p.split("=",1) for p in parts[1:] if "=" in p)
    if (not parts or parts[0] != "DMROMFSID1" or fields.get("title") != TITLE
        or fields.get("size") != "26247576430" or fields.get("index") != "b6a3def414e47ca5"):
        fail("RomFS identity doesn't match verified handoff (title/size/index): "+marker[:250])
    # The version field is NACP's display version, not necessarily the NUP's v131072.
    plist = plistlib.loads(z.read(PREFIX+"Info.plist"))
    if str(plist.get("MinimumOSVersion", "")) != "26.0":
        fail("not an iOS 26.0 IPA")
    shader_images = {x.filename:(x.file_size, x.CRC) for x in z.infolist()
                     if re.fullmatch(r"Payload/DmIOS\.app/msl/b-[^/]+\.img(?:\.[0-9]+)?", x.filename)}
    if not shader_images:
        fail("no NVN Metal image or split image parts; refusing invalid thin IPA")
    bases = {}
    for name in shader_images:
        base, dot, suffix = name.rpartition(".img")
        stem = base + ".img"
        part = suffix[1:] if suffix.startswith(".") else None
        if part is not None and not part.isdigit():
            fail("invalid shader image part name: "+name)
        bases.setdefault(stem, []).append(part)
    if len(bases)!=1:
        fail("expected exactly one NVN shader image chain")
    parts = list(bases.values())[0]
    if len(parts)==1 and parts[0] is None:
        pass  # one original image
    elif None not in parts and all(p is not None for p in parts):
        numbered = sorted(int(p) for p in parts)
        if numbered!=list(range(len(numbered))):
            fail("missing/duplicate split shader image part")
        if len(numbered)<2:
            fail("unexpected single numbered shader image part")
    else:
        fail("mixed or unexpected Metal image parts")
    if sum(size for size,_ in shader_images.values()) < 20 * 1024 * 1024:
        fail("Metal image implausibly small")
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

def patch_launcher_and_env(app, changes):
    """Update selectable launcher defaults, without freezing them via env.txt."""
    config = app/"dm"/"launcher.json"
    if not config.is_file():
        fail("missing launcher.json; can't guarantee selectable 30/60 FPS")
    data = json.loads(config.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or data.get("game") != TITLE:
        fail("invalid launcher schema or game")
    rows = data.get("settings")
    if not isinstance(rows, list):
        fail("invalid launcher settings")
    lookup = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("env"), str) or row["env"] in lookup:
            fail("invalid/duplicate launcher row")
        lookup[row["env"]] = row
    if "DM_FRAME_MODE" not in lookup:
        fail("original game launcher cannot switch between 30 and 60 FPS")
    defaults, env_only = {}, {}
    for key, value in changes.items():
        row = lookup.get(key)
        if row is None:
            env_only[key] = value
            continue
        if row.get("kind") == "choice":
            choices = {str(x[0]) for x in row.get("options", []) if isinstance(x, list) and len(x) == 2}
            if value not in choices: fail("launcher missing option "+key+"="+value)
        elif row.get("kind") == "toggle":
            if value not in (str(row.get("on")), str(row.get("off"))):
                fail("launcher toggle missing "+key+"="+value)
        elif row.get("kind") == "range":
            # Schema 1 describes ranges with numeric min/max/step, but the
            # launcher stores defaults as strings. Decimal avoids float drift.
            try:
                v, lo, hi, step = (Decimal(str(x)) for x in (value, row["min"], row["max"], row["step"]))
                with localcontext() as ctx:
                    ctx.prec = 64
                    valid = (all(x.is_finite() for x in (v, lo, hi, step))
                             and lo <= v <= hi and step > 0
                             and (v - lo) % step == 0)
            except (KeyError, TypeError, ValueError, InvalidOperation):
                valid = False
            if not valid: fail("invalid launcher range "+key+"="+value)
        else:
            fail("unsupported launcher setting: "+key)
        row["default"] = value
        defaults[key] = value
    config.write_text(json.dumps(data, ensure_ascii=False, indent=1)+"\n", encoding="utf-8")
    path = app/"dm"/"env.txt"
    old = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"): continue
            if "=" not in line: fail("invalid bundled env row")
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if not key.startswith("DM_") or key in old: fail("duplicate or non-DM key: "+key)
            old[key] = value
    owned = set().union(*(x.keys() for x in PRESETS.values()))
    final = {k:v for k,v in old.items() if k not in owned}
    final.update(env_only)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# HookLink2iOS runtime-only defaults; FPS choices are in dm/launcher.json.\n"
                    "# Saved launcher settings and Documents/env.txt can take priority.\n"+
                    "".join(f"{k}={v}\n" for k,v in final.items()), encoding="utf-8")
    if any(key in final for key in defaults): fail("launcher key locked by env")
    return {"launcher_defaults":defaults, "bundled_env":final, "preserved":{k:v for k,v in old.items() if k not in owned}}

def verify_signed_native(result, native_info):
    """Verify the *signed* executable, not the pre-codesign relink digest."""
    if not native_info.get("signed_executable_sha256") or not native_info.get("signed_executable_bytes"):
        fail("missing post-codesign native executable digest")
    native = result.getinfo(PREFIX+"DmIOS")
    if native.file_size != native_info["signed_executable_bytes"]:
        fail("signed executable size changed when packed into IPA")
    h = hashlib.sha256()
    with result.open(native) as f:
        for part in iter(lambda:f.read(CHUNK), b""):
            h.update(part)
    if h.hexdigest() != native_info["signed_executable_sha256"]:
        fail("signed executable SHA-256 changed when packed into IPA")


def rezip(root, destination, original_compression):
    """Keep the exact source ZIP entry compression method, notably split .img.N.

    NXNative compresses these images (up to 2 GB each) in the IPA.
    Storing them instead balloons a valid 3.48 GB IPA to 6.08 GB and risks
    ZIP64/sideload rejection. Changes to launcher/env are small.
    """
    with zipfile.ZipFile(destination, "w", allowZip64=True) as z:
        for path in sorted((root/"Payload").rglob("*")):
            if not path.is_file(): continue
            name = path.relative_to(root).as_posix()
            method = original_compression.get(name, zipfile.ZIP_DEFLATED)
            if method not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                fail("unsupported original ZIP compression for "+name)
            z.write(path, name, compress_type=method,
                    compresslevel=6 if method == zipfile.ZIP_DEFLATED else None)

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--source", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--report", type=Path, required=True)
    a.add_argument("--preset", choices=list(PRESETS), default="balanced30fg")
    a.add_argument("--pso-dir", type=Path, default=None, help="Optional validated A19 Pro Metal4 PSO bundle")
    a.add_argument("--replacement-executable", type=Path, default=None, help="Rebuilt native host with byte-identical embedded guest sections")
    a.add_argument("--game-icon", type=Path, default=None)
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
            methods = {info.filename:info.compress_type for info in z.infolist() if not info.is_dir()}
            unpack(z, temp/"package")
        app = temp/"package"/"Payload"/"DmIOS.app"
        executable = app/"DmIOS"
        executable.chmod(executable.stat().st_mode | 0o111)
        native_info = None
        if args.replacement_executable is not None:
            replacement = args.replacement_executable.resolve()
            if not replacement.is_file() or replacement.stat().st_size < 10*1024*1024:
                fail("missing/suspiciously small native host replacement")
            with replacement.open("rb") as f:
                mh = f.read(12)
            if len(mh)!=12 or mh[:4]!=b"\xcf\xfa\xed\xfe" or int.from_bytes(mh[4:8],"little")!=0x0100000c:
                fail("replacement is not a thin ARM64 Mach-O")
            source_executable_sha256 = sha256(executable)
            shutil.copy2(replacement,executable)
            executable.chmod(executable.stat().st_mode | 0o111)
            native_info = {"old_executable_sha256":source_executable_sha256,
                           "new_executable_sha256":sha256(executable),
                           "new_executable_bytes":executable.stat().st_size,
                           "guest_metal_shader_images_unchanged":True,
                           "source":"pinned nxnative 1.8.5 plus selectively ported X1/X2/X3 runtime code"}
        values = patch_launcher_and_env(app, PRESETS[args.preset])
        game_icon_info = None
        if args.game_icon is not None:
            import hooklink2ios_game_icon as game_icon
            game_icon_info = game_icon.install(app, args.game_icon)
        pso_info = None
        if args.pso_dir is not None:
            pso = args.pso_dir.resolve()
            arch, stamp = pso/"applegpu_g18p.mtl4a", pso/"prebuilt.tsv"
            if not arch.is_file() or arch.stat().st_size < 1024 or not stamp.is_file():
                fail("optional A19 Pro pipeline archive missing/incomplete")
            if (app/"pso").exists():
                fail("the source IPA already has a PSO directory; refusing replacement")
            for member in pso.iterdir():
                if member.is_symlink() or not member.is_file() or member.suffix not in (".mtl4a",".tsv"):
                    fail("untrusted member in optional PSO directory: " + member.name)
                if member.suffix == ".mtl4a" and member.name != "applegpu_g18p.mtl4a":
                    fail("unexpected GPU architecture in offline PSO")
            shutil.copytree(pso, app/"pso")
            pso_info = {"gpu":"applegpu_g18p","archive_sha256":sha256(arch),
                        "archive_size_bytes":arch.stat().st_size,
                        "source":"Metal4 offline PSO built from unchanged original Metal libraries"}
        for framework in sorted((app/"Frameworks").glob("*.framework")) if (app/"Frameworks").exists() else []:
            subprocess.run(["codesign","--force","--sign","-","--timestamp=none",str(framework)],check=True)
        subprocess.run(["codesign","--force","--sign","-","--timestamp=none",
                        "--entitlements",str(args.entitlements.resolve()),str(app)],check=True)
        subprocess.run(["codesign","--verify","--deep","--strict",str(app)],check=True)
        # codesign rewrites LC_CODE_SIGNATURE/__LINKEDIT; its digest differs.
        # Preserve the pre-sign digest proving the relinked guest sections, and
        # record a second digest for the signed file actually shipped.
        if native_info is not None:
            native_info["signed_executable_sha256"] = sha256(executable)
            native_info["signed_executable_bytes"] = executable.stat().st_size
            if native_info["signed_executable_bytes"] < native_info["new_executable_bytes"]:
                fail("signed native executable unexpectedly shrank")
        rezip(temp/"package", args.output, methods)
        size_limit = min(4_000_000_000, source_ipa.stat().st_size+
                         (900 if pso_info else 256)*1024*1024)
        if args.output.stat().st_size > size_limit:
            fail(f"oversized repack ({args.output.stat().st_size:,} bytes); source "
                 f"{source_ipa.stat().st_size:,}; limit {size_limit:,}. "
                 "Refuse IPA that can break iOS installers or require ZIP64.")
        with zipfile.ZipFile(args.output) as zipped:
            if audit(zipped) != original:
                fail("shader library CRC/size or RomFS identity changed")
            if game_icon_info:
                for name,digest in game_icon_info.items():
                    if hashlib.sha256(zipped.read(PREFIX+name)).hexdigest()!=digest:fail("icon bytes changed in IPA")
                icon_plist=plistlib.loads(zipped.read(PREFIX+"Info.plist"))
                if icon_plist["CFBundleIcons"]["CFBundlePrimaryIcon"]["CFBundleIconFiles"]!=["GameIcon60"]:fail("missing primary icon metadata")
            launcher = json.loads(zipped.read(PREFIX+"dm/launcher.json"))
            defaults = {r["env"]:str(r["default"]) for r in launcher["settings"]}
            env = zipped.read(PREFIX+"dm/env.txt").decode("utf-8")
            env_values = dict(line.split("=",1) for line in env.splitlines()
                              if line and not line.startswith("#") and "=" in line)
            for key,value in PRESETS[args.preset].items():
                if key in defaults:
                    if defaults[key] != value or key in env_values:
                        fail("launcher preset not applied cleanly: "+key)
                elif env_values.get(key) != value:
                    fail("env-only preset missing: "+key)

        if native_info:
            with zipfile.ZipFile(args.output) as result:
                verify_signed_native(result, native_info)
        if pso_info:
            with zipfile.ZipFile(args.output) as result:
                name = PREFIX+"pso/applegpu_g18p.mtl4a"
                if name not in result.namelist():
                    fail("offline pipeline archive missing from repacked IPA")
                h = hashlib.sha256()
                size = 0
                with result.open(name) as data:
                    for block in iter(lambda: data.read(CHUNK), b""):
                        h.update(block)
                        size += len(block)
                if size != pso_info["archive_size_bytes"] or h.hexdigest() != pso_info["archive_sha256"]:
                    fail("PSO integrity changed during IPA packing")
        report = {
          "project":"HookLink2iOS", "title_id":TITLE, "type":"settings-only-repack",
          "preset":args.preset, "settings":values, "launcher_patched":True,
          "source_sha256":sha256(args.source), "source_ipa_sha256":sha256(source_ipa),
          "output_name":args.output.name, "output_sha256":sha256(args.output),
          "output_size":args.output.stat().st_size,
          "shader_images_preserved":len(original[1]), "romfs_external":True,
          "engine_updated":bool(native_info), "shader_recompiled":False, "game_code_recompiled":False,
          "source_engine_not_provable_from_bare_ipa":True,
          "offline_pso":pso_info, "native_host_relinked":native_info, "game_icon":game_icon_info,
          "signature":"ad-hoc; sideload installer may re-sign using player's identity",
          "note":"Saved launcher choices override defaults; DM_FRAME_MODE remains selectable"}
        args.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,indent=2),flush=True)
        print("HOOKLINK2IOS_REPACK_OK",flush=True)

if __name__ == "__main__":
    main()
