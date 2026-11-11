#!/usr/bin/env python3
"""Rebuild only the BOTW Route-C host framework from an existing IPA.

The original game modules, shader libraries, RomFS/AOC and app shell are preserved.
Only dm/gfx/nvn/nvn_mtl.m is patched and the DmShellGame host framework binary is
relinked around the exact ARM64 module sections extracted from the source IPA.
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

TITLE_ID = "01007EF00011E000"
FRAMEWORK_NAME = f"DmGame{TITLE_ID}.framework"
IGNORED_SOURCE_RUN_NUMBERS = {6}
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
UPSTREAM_OPTIMIZATION = "3304d6a0d7edebc4bb5b57c73e6d7b431721c8f5"


def fail(message: str) -> None:
    raise SystemExit("[Link2iOS optimize] ERROR: " + message)


def log(message: str) -> None:
    print("[Link2iOS optimize] " + message, flush=True)


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-zip", type=Path, required=True)
    ap.add_argument("--source-artifact-id", type=int, required=True)
    ap.add_argument("--source-artifact-name", required=True)
    ap.add_argument("--source-run-id", type=int, required=True)
    ap.add_argument("--source-run-number", type=int, required=True)
    ap.add_argument("--nx2apple-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    args = ap.parse_args()
    if args.source_artifact_id <= 0 or args.source_run_id <= 0 or args.source_run_number <= 0:
        fail("source artifact/run identifiers must be positive integers")
    if args.source_run_number in IGNORED_SOURCE_RUN_NUMBERS:
        fail(f"source run #{args.source_run_number} is explicitly excluded from the optimization chain")
    expected_source_name = f"Link2iOS-BOTW-Optimized-{args.source_run_number}"
    if args.source_artifact_name != expected_source_name:
        fail(f"source artifact name does not match its run number: {args.source_artifact_name!r}")

    artifact_zip = args.artifact_zip.resolve()
    nx = args.nx2apple_root.resolve()
    output = args.output.resolve()
    work = args.work.resolve()
    repo = Path(__file__).resolve().parents[1]
    patch = repo / "scripts/patches/botw-metal4-encode-thread.patch"
    if not artifact_zip.is_file() or not patch.is_file():
        fail("artifact ZIP or the pinned Metal optimization patch is missing")
    if (nx / ".upstream-ref").read_text(encoding="utf-8").strip() != ENGINE_PIN:
        fail("NX2Apple upstream pin does not match the source IPA")
    engine = nx / "engine"
    ios = engine / "dm/ios"
    host = engine / "dm/host"
    if not (ios / "project-framework.yml").is_file() or not (ios / "framework/ShellGlue.m").is_file():
        fail("the synced NX2Apple tree lacks the Route-C DmShellGame target")
    if not (engine / "dm/gfx/nvn/nvn_mtl.m").is_file():
        fail("the NXNative Metal NVN source is missing")

    output.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    source_ipa = work / "source.ipa"
    with zipfile.ZipFile(artifact_zip) as z:
        files = [i for i in z.infolist() if not i.is_dir()]
        ipas = [i for i in files if i.filename.lower().endswith(".ipa")]
        reports = [i for i in files if PurePosixPath(i.filename).name == "build-report.json"]
        if len(ipas) != 1 or len(reports) != 1:
            fail(f"source artifact must contain exactly one IPA and one report; found {len(ipas)} IPA(s), {len(reports)} report(s)")
        report_tmp = work / "source-build-report.json"
        copy_zip_member(z, reports[0], report_tmp)
        source_report = json.loads(report_tmp.read_text(encoding="utf-8"))
        if source_report.get("project") != "Link2iOS" or source_report.get("title_id") != TITLE_ID:
            fail("source artifact report does not identify the expected Link2iOS BOTW build")
        if source_report.get("engine_pin") != ENGINE_PIN:
            fail("source IPA was not produced from the exact pinned NX2Apple engine revision")
        if source_report.get("rebuilt_host_framework") is not True or source_report.get("reused_game_modules_verbatim") is not True:
            fail("source artifact is not a prior host-optimized IPA with the original BOTW modules preserved")
        if source_report.get("recompiled_game_framework") is not False:
            fail("source artifact report does not prove that BOTW game modules were reused")
        if source_report.get("render_quality_reduced") is not False or source_report.get("resolution_changed") is not False:
            fail("source artifact report indicates a graphics-quality or resolution reduction")
        prior_hash = source_report.get("optimized_framework_executable_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", str(prior_hash)):
            fail("source artifact report lacks a valid optimized framework SHA-256; refusing to restart from an unoptimized IPA")
        copy_zip_member(z, ipas[0], source_ipa)
    log(f"source chain: run #{args.source_run_number}, run_id={args.source_run_id}, artifact={args.source_artifact_id} ({args.source_artifact_name})")
    log(f"source IPA verified: {source_ipa.stat().st_size:,} bytes; no game assets will be rebuilt")

    unpack = work / "unpacked"
    unpack.mkdir()
    run(["/usr/bin/unzip", "-q", source_ipa, "-d", unpack])
    apps = list((unpack / "Payload").glob("*.app"))
    if len(apps) != 1 or apps[0].name != "DmShell.app":
        fail("source IPA must contain exactly one Payload/DmShell.app")
    app = apps[0]
    fw = app / "Frameworks" / FRAMEWORK_NAME
    info_path = fw / "Info.plist"
    if not info_path.is_file():
        fail(f"source IPA lacks {FRAMEWORK_NAME}/Info.plist")
    fw_info = plistlib.loads(info_path.read_bytes())
    executable = fw_info.get("CFBundleExecutable")
    old_binary = fw / str(executable or "")
    if not executable or not old_binary.is_file():
        fail("source game framework executable is missing")
    manifest_path = fw / "game.manifest.json"
    if not manifest_path.is_file():
        fail("source game framework manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("title_id") != TITLE_ID or manifest.get("framework") != FRAMEWORK_NAME or manifest.get("loader") != "FH":
        fail("source game framework manifest is not the expected Route-C FH BOTW framework")
    game_profile = fw / "profile.tsv"
    if not game_profile.is_file():
        fail("source game profile.tsv is missing")
    profile_text = game_profile.read_text(encoding="utf-8")
    if "fps_target\t60" not in profile_text or "op_mode\thandheld" not in profile_text:
        fail("source game profile must preserve Handheld mode and the 60 FPS target")

    old_hash = sha256(old_binary)
    if old_hash != prior_hash:
        fail("source framework executable SHA-256 does not match the previous optimized build report; lineage is broken")

    # Reset Gen before writing the Mach-O assembly: otherwise the cleanup would delete embed.S.
    gen = ios / "Gen"
    shutil.rmtree(gen, ignore_errors=True)
    (gen / "dm").mkdir(parents=True)
    (gen / "framework" / "dm").mkdir(parents=True)
    embed = gen / "embed.S"
    segment_flags = embedded_section_assembly(old_binary, manifest, embed)
    if len(manifest["modules"]) != 3:
        fail(f"expected BOTW's 3 already-compiled modules, found {len(manifest['modules'])}")
    log("guest modules extracted as linker sections: " + ", ".join(manifest["modules"]))
    log("module bytes are reused verbatim from the source IPA")

    # Reuse every game-specific resource byte-for-byte. The engine is rebuilt, not the game.
    shutil.copytree(fw / "dm", gen / "framework" / "dm", dirs_exist_ok=True)
    shutil.copy2(game_profile, gen / "framework/profile.tsv")
    shutil.copy2(manifest_path, gen / "framework/game.manifest.json")

    # The existing app's display metadata and entitlements define the rebuilt framework's product identity.
    app_info = plistlib.loads((app / "Info.plist").read_bytes())
    app_executable = app_info.get("CFBundleExecutable", "DmShell")
    app_bin = app / str(app_executable)
    if not app_bin.is_file():
        fail("source DmShell executable is missing")
    entitlements_path = work / "DmShell.entitlements"
    entitlements = extract_entitlements(app_bin, entitlements_path)
    env = os.environ.copy()
    env.update({
        "GAME": TITLE_ID,
        "DM_GAME": TITLE_ID,
        "DM_BUNDLE_ID": str(fw_info.get("CFBundleIdentifier", "org.nxnative.link2ios.DmGame")),
        "DM_DISPLAY_NAME": str(fw_info.get("CFBundleDisplayName", app_info.get("CFBundleDisplayName", "Link2iOS"))),
        "DM_APP_VERSION": str(fw_info.get("CFBundleShortVersionString", "1.0.0")),
        "DM_TEAM_ID": str(fw_info.get("DEVELOPMENT_TEAM", "0000000000")),
        "DM_SCHEME_NAME": "DmIOS",
        "DM_APP_CATEGORY": str(app_info.get("LSApplicationCategoryType", "public.app-category.adventure-games")),
        "DM_SHOW_FPS": "YES" if str(app_info.get("DMShowFPS", "YES")).upper() in ("YES", "1", "TRUE") else "NO",
        "DM_LANG": str(app_info.get("DMLanguage", "pt-BR")),
    })

    # Apply the reviewed host-only upstream optimization to this exact pinned tree.
    run(["git", "apply", "--check", patch], cwd=engine)
    run(["git", "apply", patch], cwd=engine)

    # BOTW's current profile uses full draw-pass barriers. Use NVN's game-barrier
    # ordering: the next pass may overlap its vertex stage with the previous
    # pass's fragments, while explicit NVN barriers and copy/compute dependencies
    # still serialize. This does not change shaders, render scale or visual assets.
    # Keep this BOTW-only in the pinned tree and verify the generated compile-time flag.
    game_profile_path = engine / "dm/games" / TITLE_ID / "game.tsv"
    if not game_profile_path.is_file():
        fail("pinned NX2Apple tree lacks the BOTW game profile")
    profile_lines = game_profile_path.read_text(encoding="utf-8").splitlines()
    dbr_rows = [i for i, line in enumerate(profile_lines) if line.split("\t", 1)[0] == "draw_barriers"]
    if len(dbr_rows) > 1:
        fail("BOTW game profile has duplicate draw_barriers keys")
    if dbr_rows:
        profile_lines[dbr_rows[0]] = "draw_barriers\tgame"
    else:
        profile_lines += ["", "# iOS GPU overlap trial: keep NVN's explicit game barriers; overlap independent pass stages",
                          "draw_barriers\tgame"]
    game_profile_path.write_text("\n".join(profile_lines) + "\n", encoding="utf-8")
    log("BOTW GPU ordering: draw_barriers=game (explicit game barriers retained; no render-scale or shader changes)")

    # Recreate the host's normal iOS compile settings from its Makefile, without touching game assets.
    cfg = gen / "dm.xcconfig"
    p = subprocess.run([sys.executable, str(ios / "tools/gen_build.py"), str(host), str(gen)],
                       cwd=ios, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        fail("gen_build.py failed:\n" + (p.stderr or p.stdout)[-12000:])
    if not p.stdout.strip() or "HEADER_SEARCH_PATHS =" not in p.stdout:
        fail("gen_build.py did not produce the iOS compiler settings:\n" + p.stdout[-4000:] + "\n" + p.stderr[-4000:])

    profile_header = host / "gen" / TITLE_ID / "game_profile.h"
    if not profile_header.is_file() or "#define DM_GAME_DRAW_BARRIERS_GAME 1" not in profile_header.read_text(encoding="utf-8"):
        fail("generated game_profile.h does not enable BOTW draw_barriers=game; refusing to build an unchanged renderer")
    cfg.write_text(p.stdout.rstrip() + "\nOTHER_LDFLAGS = $(inherited) $(DM_FRAMEWORKS) " + " ".join(segment_flags) + "\n", encoding="utf-8")

    # XcodeGen validates all targets in the spec, even though this job builds only DmShellGame.
    (gen / "Assets.xcassets").mkdir(parents=True, exist_ok=True)
    (gen / "Assets.xcassets/Contents.json").write_text(
        json.dumps({"info": {"author": "xcode", "version": 1}}) + "\n", encoding="utf-8")
    (gen / "framework.xcconfig").write_text(
        "OTHER_LDFLAGS = $(inherited) " + " ".join(segment_flags) + "\n", encoding="utf-8")

    run(["xcodegen", "generate", "-q", "--spec", "project-framework.yml"], cwd=ios, env=env)
    products = work / "products"
    objects = work / "objects"
    products.mkdir()
    objects.mkdir()
    xcode_log = work / "xcodebuild-framework.log"
    run([
        "xcodebuild", "-project", ios / "DmIOS.xcodeproj",
        "-target", "DmShellGame", "-configuration", "Release",
        "-sdk", "iphoneos", "-arch", "arm64",
        f"PRODUCT_NAME={executable}",
        f"PRODUCT_BUNDLE_IDENTIFIER={fw_info.get('CFBundleIdentifier', 'org.nxnative.link2ios.DmGame')}",
        f"MARKETING_VERSION={fw_info.get('CFBundleShortVersionString', '1.0.0')}",
        f"CURRENT_PROJECT_VERSION={fw_info.get('CFBundleVersion', '1')}",
        f"SYMROOT={products}", f"OBJROOT={objects}",
        "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO", "CODE_SIGN_IDENTITY=",
        "build",
    ], cwd=ios, env=env, log_file=xcode_log)

    release = products / "Release-iphoneos"
    candidates = []
    for built_fw in release.glob("*.framework"):
        built_info_path = built_fw / "Info.plist"
        if not built_info_path.is_file():
            continue
        built_info = plistlib.loads(built_info_path.read_bytes())
        built_exe = built_fw / str(built_info.get("CFBundleExecutable", ""))
        if built_exe.is_file():
            symbols = run(["nm", "-gU", built_exe], capture=True).stdout
            if all(sym in symbols for sym in ("_dm_glue_start_game", "_dm_glue_present_game", "_dm_glue_focus_event")):
                candidates.append(built_exe)
    if len(candidates) != 1:
        fail(f"xcodebuild must produce exactly one DmShellGame framework with glue exports; found {len(candidates)}")
    new_binary = candidates[0]
    new_sections = otool_sections(new_binary)
    old_sections = otool_sections(old_binary)
    for key in old_sections:
        if key[1].startswith("__dm") or key[0].startswith("__DM"):
            if key not in new_sections:
                fail(f"rebuilt framework lost embedded module section {key[0]},{key[1]}")
            if old_sections[key]["size"] != new_sections[key]["size"]:
                fail(f"embedded source section size changed for {key[0]},{key[1]}")
    required_exports = ("_dm_glue_version", "_dm_glue_start_game", "_dm_glue_present_game", "_dm_glue_focus_event")
    symbols = run(["nm", "-gU", new_binary], capture=True).stdout
    if not all(sym in symbols for sym in required_exports):
        fail("rebuilt framework is missing one or more required Route-C glue exports")
    new_hash = sha256(new_binary)

    # Replace only the host framework executable. Keep the original framework resources, Metal libraries,
    # pipeline tables, icon and guest modules exactly as they were.
    shutil.copy2(new_binary, old_binary)
    run(["xattr", "-cr", fw])
    run(["codesign", "--force", "--sign", "-", "--timestamp=none", fw])
    run(["codesign", "--verify", "--strict", fw])
    run(["codesign", "--force", "--sign", "-", "--entitlements", entitlements_path,
         "--timestamp=none", app])
    run(["codesign", "--verify", "--deep", "--strict", app])

    optimized_ipa = output / "Link2iOS-BOTW-Optimized.ipa"
    packer = engine / "dm/ios/tools/pack_ipa.py"
    run([sys.executable, packer, optimized_ipa, "--no-reuse", f"Payload/DmShell.app={app}"], cwd=engine)
    with zipfile.ZipFile(optimized_ipa) as z:
        names = set(z.namelist())
        required_files = {
            "Payload/DmShell.app/DmShell",
            f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/{executable}",
            f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/profile.tsv",
            f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/game.manifest.json",
            f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/msl/b-0c434f1b68df.img",
        }
        missing = sorted(n for n in required_files if n not in names)
        if missing:
            fail("optimized IPA is missing preserved runtime resources: " + ", ".join(missing))
        final_manifest = json.loads(z.read(f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/game.manifest.json"))
        if final_manifest.get("title_id") != TITLE_ID or final_manifest.get("loader") != "FH":
            fail("optimized IPA game manifest verification failed")
        final_profile = z.read(f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/profile.tsv").decode()
        if "fps_target\t60" not in final_profile:
            fail("optimized IPA no longer has the 60 FPS game profile")

    report = {
        "project": "Link2iOS",
        "game": "The Legend of Zelda: Breath of the Wild",
        "title_id": TITLE_ID,
        "source_artifact_id": args.source_artifact_id,
        "source_artifact_name": args.source_artifact_name,
        "source_run_id": args.source_run_id,
        "source_run_number": args.source_run_number,
        "source_run": source_report.get("source_run"),
        "engine_pin": ENGINE_PIN,
        "upstream_optimization_commit": UPSTREAM_OPTIMIZATION,
        "modified_host_source": ["dm/gfx/nvn/nvn_mtl.m"],
        "rebuilt_host_framework": True,
        "rebuilt_shared_shell": False,
        "recompiled_game_framework": False,
        "reused_game_modules_verbatim": True,
        "reused_romfs_aoc": True,
        "reused_shader_libraries": True,
        "reused_pipeline_archive": True,
        "source_framework_executable_sha256": old_hash,
        "optimized_framework_executable_sha256": new_hash,
        "module_list": manifest["modules"],
        "profile_preserved": {"op_mode": "handheld", "fps_target": 60},
        "render_quality_reduced": False,
        "resolution_changed": False,
        "frame_pacing_settings_changed": False,
        "memory_entitlements_preserved": bool(entitlements.get("com.apple.developer.kernel.increased-memory-limit")),
        "ipa_size_bytes": optimized_ipa.stat().st_size,
    }
    (output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    log(f"OPTIMIZED_IPA_READY {optimized_ipa} ({optimized_ipa.stat().st_size:,} bytes)")
    log("Only the host framework was rebuilt; BOTW module and resource payloads were reused.")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
