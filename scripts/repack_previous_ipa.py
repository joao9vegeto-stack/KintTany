#!/usr/bin/env python3
"""Repackage the proven BOTW framework from build #3 without rebuilding game code."""
from __future__ import annotations
import argparse, json, os, plistlib, shutil, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath
import build_shared

SOURCE_RUN = 42856404863
TITLE_ID = "01007EF00011E000"
PACKAGE_VERSION = "v1114112"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
FRAMEWORK_NAME = f"DmGame{TITLE_ID}.framework"

def fail(message):
    raise SystemExit("[Link2iOS repack] ERROR: " + message)

def run(command, cwd=None, env=None):
    command = list(map(str, command))
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)

def extract_member(archive, member, root):
    rel = PurePosixPath(member.filename)
    if rel.is_absolute() or ".." in rel.parts:
        fail("unsafe artifact path: " + member.filename)
    target = root.joinpath(*[p for p in rel.parts if p not in ("", ".")])
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member) as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=16 * 1024 * 1024)
    return target

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-zip", type=Path, required=True)
    ap.add_argument("--nx2apple-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    nx, output = args.nx2apple_root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (nx / ".upstream-ref").read_text().strip() != ENGINE_PIN:
        fail("NXNative pin mismatch; expected " + ENGINE_PIN)

    source_dir = output / "source-build-3"
    shutil.rmtree(source_dir, ignore_errors=True)
    source_dir.mkdir(parents=True)
    with zipfile.ZipFile(args.artifact_zip) as z:
        entries = [x for x in z.infolist() if not x.is_dir()]
        ipas = [x for x in entries if x.filename.lower().endswith(".ipa")]
        reports = [x for x in entries if PurePosixPath(x.filename).name == "build-report.json"]
        if len(ipas) != 1 or len(reports) != 1:
            fail(f"build #3 artifact contents unexpected: {len(ipas)} IPA(s), {len(reports)} report(s)")
        report_path = extract_member(z, reports[0], source_dir)
        report = json.loads(report_path.read_text())
        expected = {"project":"Link2iOS", "title_id":TITLE_ID,
                    "package_version":PACKAGE_VERSION, "engine_pin":ENGINE_PIN,
                    "framework":FRAMEWORK_NAME}
        for key, value in expected.items():
            if report.get(key) != value:
                fail(f"build #3 report mismatch for {key}: {report.get(key)!r}")
        ipa_source = extract_member(z, ipas[0], source_dir)
    print(f"Verified successful source build #3 (run {SOURCE_RUN}).", flush=True)

    unpacked = output / "source-payload"
    shutil.rmtree(unpacked, ignore_errors=True)
    unpacked.mkdir(parents=True)
    run(["/usr/bin/unzip", "-q", ipa_source, "-d", unpacked])
    apps = list((unpacked / "Payload").glob("*.app"))
    if len(apps) != 1 or apps[0].name != "DmShell.app":
        fail("source IPA must contain exactly one DmShell.app")
    framework = apps[0] / "Frameworks" / FRAMEWORK_NAME
    if not framework.is_dir():
        fail("source IPA does not contain " + FRAMEWORK_NAME)
    manifest_path = framework / "game.manifest.json"
    if not manifest_path.is_file():
        fail("reused framework manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    if str(manifest.get("title_id","")).upper() != TITLE_ID or manifest.get("framework") != FRAMEWORK_NAME:
        fail("reused framework manifest does not identify BOTW")
    if manifest.get("loader") != "FH":
        fail("reused framework is not the Route C FH loader")

    profile = framework / "profile.tsv"
    if not profile.is_file():
        fail("reused BOTW framework lacks profile.tsv")
    lines = profile.read_text(encoding="utf-8").splitlines()
    op_rows = [i for i,line in enumerate(lines) if line.partition("\t")[0] == "op_mode"]
    if len(op_rows) > 1:
        fail("duplicate op_mode rows in reused profile")
    if op_rows:
        if len(lines[op_rows[0]].split("\t")) != 2:
            fail("malformed op_mode row in reused profile")
        lines[op_rows[0]] = "op_mode\thandheld"
    else:
        lines.append("op_mode\thandheld")
    fps_rows = [line.split("\t") for line in lines if line.partition("\t")[0] == "fps_target"]
    if len(fps_rows) != 1 or len(fps_rows[0]) != 2 or fps_rows[0][1] != "60":
        fail("reused profile must retain exactly one fps_target=60 row")
    profile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if "op_mode\thandheld" not in profile.read_text() or "fps_target\t60" not in profile.read_text():
        fail("Handheld/60 FPS profile verification failed")
    print("Reused framework profile patched: handheld, 60 FPS retained.", flush=True)

    icon = framework / "icon.png"
    if not icon.is_file():
        fail("build #3 framework lacks its embedded BOTW NACP icon.png; no generic fallback allowed")
    dims = subprocess.run(["sips","-g","pixelWidth","-g","pixelHeight",icon],
                           capture_output=True,text=True,check=True).stdout
    vals = {}
    for line in dims.splitlines():
        if "pixelWidth:" in line: vals["w"] = line.rsplit(":",1)[1].strip()
        if "pixelHeight:" in line: vals["h"] = line.rsplit(":",1)[1].strip()
    if not vals.get("w") or vals["w"] != vals.get("h"):
        fail("BOTW framework icon is not square: " + dims)
    build_shared.patch_shell_icon_pipeline(nx / "engine")

    shell_dir, derived = output / "shell-project", output / "shell-derived-data"
    shutil.rmtree(shell_dir, ignore_errors=True)
    shutil.rmtree(derived, ignore_errors=True)
    shell_dir.mkdir(parents=True)
    env = os.environ.copy()
    env.update({
        "SHELL_DIR":str(shell_dir), "DM_SHELL_FRAMEWORKS":str(framework),
        "DM_SHELL_PACKAGE":str(nx / "frontend-ios"), "DM_SHELL_NAME":"Link2iOS",
        "DM_BUNDLE_ID":"org.nxnative.link2ios", "DM_APP_VERSION":"1.0.0",
        "DM_TEAM_ID":"0000000000", "DM_XCODE_DERIVED_DATA":str(derived),
        "FONT_PY":sys.executable, "STD_FONT":"/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "DM_SHELL_ICON_SOURCE":str(icon),
    })
    engine = nx / "engine"
    print("Rebuilding only Shared Shell; game framework and Metal libraries are reused.", flush=True)
    run(["bash",engine / "dm/ios/tools/build_shell.sh","--build"],cwd=engine,env=env)

    app = derived / "Build/Products/Release-iphoneos/DmShell.app"
    if not (app / "DmShell").is_file() or not (app / "Assets.car").is_file():
        fail("Shared Shell executable or Assets.car missing")
    if not (shell_dir / "Gen/Assets.xcassets/AppIcon.appiconset/AppIcon.png").is_file():
        fail("BOTW NACP AppIcon was not staged")
    info = plistlib.loads((app / "Info.plist").read_bytes())
    primary = info.get("CFBundleIcons",{}).get("CFBundlePrimaryIcon",{})
    if primary.get("CFBundleIconName") != "AppIcon":
        fail("Info.plist does not reference the BOTW AppIcon")
    entitlements = shell_dir / "Gen/DmShell.entitlements"
    if not entitlements.is_file():
        fail("DmShell.entitlements missing")
    embedded = sorted((app / "Frameworks").glob("*.framework"))
    if not any(x.name == FRAMEWORK_NAME for x in embedded):
        fail("Shared Shell did not embed the reused BOTW framework")
    for item in embedded:
        run(["xattr","-cr",item])
        run(["codesign","--force","--sign","-","--timestamp=none",item])
        run(["codesign","--verify","--strict",item])
    run(["xattr","-cr",app])
    run(["codesign","--force","--sign","-","--entitlements",entitlements,
         "--timestamp=none",app])
    run(["codesign","--verify","--deep","--strict",app])
    ent = subprocess.run(["codesign","-d","--entitlements",":-",app / "DmShell"],
                         capture_output=True,text=True,check=False)
    if "com.apple.developer.kernel.increased-memory-limit" not in (ent.stdout + ent.stderr):
        fail("ad-hoc signature lacks Increased Memory Limit")

    ipa = output / "Link2iOS-BOTW.ipa"
    run([sys.executable,engine / "dm/ios/tools/pack_ipa.py",ipa,"--no-reuse",
         f"Payload/DmShell.app={app}"],cwd=engine)
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        required = ["Payload/DmShell.app/DmShell",
                    f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/{FRAMEWORK_NAME.removesuffix('.framework')}",
                    f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/profile.tsv",
                    f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/game.manifest.json",
                    "Payload/DmShell.app/Assets.car"]
        missing = [n for n in required if n not in names]
        if missing: fail("IPA missing components: " + ", ".join(missing))
        bad = [n for n in names if n.lower().endswith("/romfs.img") or "/aoc/" in n.lower()
               or n.lower().endswith(".nsp") or n.lower().endswith("/prod.keys")
               or n.lower().endswith(".mtl4a")]
        if bad: fail("IPA contains prohibited game data: " + ", ".join(bad[:20]))
        final_profile = z.read(f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/profile.tsv").decode()
        if "op_mode\thandheld" not in final_profile or "fps_target\t60" not in final_profile:
            fail("final IPA does not preserve Handheld/60 FPS profile")

    report = {
        "project":"Link2iOS", "game":"The Legend of Zelda: Breath of the Wild",
        "title_id":TITLE_ID, "package_version":PACKAGE_VERSION, "engine_pin":ENGINE_PIN,
        "framework":FRAMEWORK_NAME, "source_run":SOURCE_RUN,
        "reused_game_framework":True, "recompiled_game_framework":False,
        "reused_metal_libraries":True, "rebuilt_shared_shell_only":True,
        "runtime_defaults":{"op_mode":"handheld","fps_target":60,
                            "adaptive_frame_step":"preserved from build #3"},
        "home_screen_icon":"BOTW NACP icon.png in reused framework, compiled into AppIcon/Assets.car",
        "signature":"ad-hoc; sideloading re-sign is required",
        "ipa_size_bytes":ipa.stat().st_size
    }
    (output / "build-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)
    print(f"IPA ready: {ipa} ({ipa.stat().st_size:,} bytes)",flush=True)

if __name__ == "__main__":
    main()
