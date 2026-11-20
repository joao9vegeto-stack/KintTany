#!/usr/bin/env python3
"""Finish the pinned Route C build on macOS from Colab-prepared NXNative artifacts.

This intentionally does NOT call builder.main(): main() scans NSPs, decrypts packages,
extracts RomFS/DLC, rewrites modules and splits shaders. Those are Colab/Linux stages.
The macOS stage reuses the recorded split key, compiles iOS Metal libraries, invokes
build_ipa.sh with DM_FRAMEWORK_ONLY, then builds the Shared Shell.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

TITLE_ID = "0100CFA00CC74000"
NX2APPLE_REF = "BladesTime"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"


def fail(message: str) -> None:
    raise SystemExit("[BladesTime] ERROR: " + message)


def run(command, cwd=None, env=None) -> None:
    command = list(map(str, command))
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def load_builder(engine: Path):
    for path in (engine / "dm/tools", engine / "dm/games", engine / "dm/gfx/tools", engine / "scripts"):
        sys.path.insert(0, str(path))
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    spec = importlib.util.spec_from_file_location("bladestime_nxnative_builder", script)
    if spec is None or spec.loader is None:
        fail(f"could not load the pinned NXNative helpers: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    import game as game_profiles
    import nacp
    import profile_guess as pg
    # main() normally imports these in its local scope; the Route C finalizer calls
    # the same helpers directly, so expose the same module globals it would create.
    module.gamemod = game_profiles
    module.nacp = nacp
    module.pg = pg
    return module, game_profiles, nacp, pg



def validate_workspace(d, work, nx, builder, gp):
    if d.get("project") != "BladesTime" or d.get("title_id") != TITLE_ID:
        fail("wrong prepared game")
    if d.get("engine_pin") != ENGINE_PIN or (nx / ".upstream-ref").read_text().strip() != ENGINE_PIN:
        fail("engine pin mismatch")
    prep = json.loads((work / "bladestime-linux-prep.json").read_text())
    for key in ("title_id", "package_version", "engine_pin", "graphics", "shader_chain",
                "shader_package_key", "modules", "provisional"):
        if prep.get(key) != d.get(key):
            fail(f"Linux/Actions prepared mismatch: {key}")
    version = work / "extract" / d["package_version"]
    romfs = version / "RomFS.img"
    patched = work / f"patched_{d['package_version']}"
    if not romfs.is_file() or not patched.is_dir() or romfs.stat().st_size != prep["romfs_size"]:
        fail("RomFS / rewritten modules missing")
    if prep.get("provisional"):
        profile_root = work / "profile"
        if not (profile_root / TITLE_ID / "game.tsv").is_file():
            fail("provisional profile missing")
        os.environ["DM_GAMES_DIR"] = str(profile_root)
        os.environ["DM_GAMES_FIRST"] = "1"
    profile = gp.load(TITLE_ID)
    modules = profile.modules_in(version / "ExeFS")
    if sorted(modules) != sorted(d["modules"]):
        fail("rewritten module names changed")
    for name in modules:
        for suffix in (".patched.bin", ".fixups.tsv"):
            if not (patched / (name + suffix)).is_file():
                fail(f"module rewrite missing: {name}{suffix}")
    if prep["graphics"] == "nvn":
        key = prep.get("shader_package_key") or ""
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            fail("NVN shader key missing")
        if builder.package_key(work / "shader" / "pkg") != key:
            fail("NVN shader package content mismatch")
    if (work / "aoc").exists() and list((work / "aoc").glob("*.img")):
        fail("unexpected Blades of Time DLC")
    return profile, version, romfs, patched, prep



def stage_nvn_shader_payload(ios: Path, framework: Path, chain: str) -> dict:
    """Keep the real compiled Metal libraries inside the thin framework.

    DM_FRAMEWORK_ONLY intentionally leaves shaders out of the framework. The
    Shared Shell will not launch a game without a matching msl/b-<chain>.img
    (or an external DMMSLTR1 trailer). Colab uploaded the base RomFS only.
    The shader image must therefore be copied into the signed framework.
    """
    source = ios / f"b-{chain}.img"
    if not source.is_file() or source.stat().st_size <= 32:
        fail(f"compiled iOS shader image is missing/empty: {source}")
    destination = framework / "msl" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if destination.stat().st_size != source.stat().st_size:
        fail("the framework shader image is truncated")
    digest = hashlib.sha256()
    with destination.open("rb") as inp:
        for chunk in iter(lambda: inp.read(1024 * 1024), b""):
            digest.update(chunk)
    result = {
        "path": f"msl/{source.name}",
        "bytes": destination.stat().st_size,
        "sha256": digest.hexdigest(),
        "library_source": str(source),
    }
    print("[BladesTime] Bundled compiled NVN shaders into framework:", result, flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--prepared-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        fail("Actions finalization requires macOS")
    nx = args.nx2apple_root.resolve()
    engine = nx / "engine"
    prepared = json.loads(args.prepared_json.read_text())
    work = Path(prepared["work_dir"]).resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # The current BladesTime/NX2Apple Shell lives here, NOT in dm/ios/tools/build_shell.sh.
    shell_script = nx / "frontend-ios" / "Shell" / "build_shell.sh"
    if not shell_script.is_file():
        fail(f"modern frontend-ios Shared Shell script missing: {shell_script}")
    if prepared.get("provisional"):
        os.environ["DM_GAMES_DIR"] = str(work / "profile")
        os.environ["DM_GAMES_FIRST"] = "1"
    builder, game_profiles, nacp, pg = load_builder(engine)
    profile, version, romfs, patched, prep = validate_workspace(
        prepared, work, nx, builder, game_profiles)
    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(exist_ok=True)
    (work / "ipa").mkdir(exist_ok=True)
    py = sys.executable
    env = builder.tool_env()
    env.update({"DM_GAME": TITLE_ID, "DM_ROOT": str(work),
                "WORK": str(work / "tmp"), "IOS_PULL": "1"})
    if prepared.get("provisional"):
        env["DM_GAMES_DIR"] = str(work / "profile")
        env["DM_GAMES_FIRST"] = "1"
    xlate = engine / "dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate"
    builder.PROG.mode = "lines"
    builder.PROG.plan(4)
    try:
        builder.check_prereqs(env, xlate, mac=False)
        builder.chain_header(py, engine, env, logs)
        actual_chain = builder.chain_of(engine)
        if actual_chain != prepared["shader_chain"]:
            fail("shader translation chain drift between Colab and Mac")
        facts = pg.build_sources(version / "ExeFS", builder.rfs.source(version),
                                 profile.modules_in(version / "ExeFS"))
        gfx = facts["graphics"][0]
        if gfx != prepared["graphics"]:
            fail("graphics backend drift between Colab and Actions")
        for key in ("glslc_capture", "vk_capture", "gl_capture", "ue_decode",
                    "oodle_packs", "ue_legacy"):
            if facts.get(key, (False, ""))[0]:
                fail(f"graphics requires a game-owned runtime capture/decoder ({key}). "
                     "No capture or extra shader results were fabricated.")
        if gfx == "nvn":
            builder.check_metal(py, engine, env)
            gpus = builder.ios_gpus("none", profile)
            pulling = builder.ios_wants_pulling(profile, gpus, False, env)
            ios = builder.build_shaders(py, engine, work / "shader", xlate, env, logs,
                                        profile, pkg_key=prep["shader_package_key"],
                                        mac=False, seen=None, pull=pulling)
            chain_lib = ios / f"b-{actual_chain}"
            if not (chain_lib.is_dir() or Path(str(chain_lib) + ".img").is_file()):
                fail("NVN iOS Metal shader library missing")
        elif gfx == "gl":
            ios = builder.build_gl_shaders(py, engine,
                [builder.rfs.source(version), version / "ExeFS/main"],
                work / "shader", env, logs, profile,
                mac=False, provisional=bool(prep["provisional"]),
                fixed=bool(facts.get("gl_fixed", (False, ""))[0]))
        elif gfx == "vulkan":
            ios = builder.build_vk_shaders(py, engine,
                [builder.rfs.source(version), version / "ExeFS/main"],
                work / "shader", env, logs, profile,
                mac=False, provisional=bool(prep["provisional"]))
        else:
            fail(f"unsupported graphics API: {gfx}")
        control = builder.languages_control(version)
        display_name = nacp.name(control) or "Blades of Time"
        display_version = nacp.version(version / "control.nacp") or "1.0.0"
        language = builder.game_language("en-US", False, nacp.languages(control))
        icon = version / "icon.jpg"
        fw_root = output / "frameworks"
        shutil.rmtree(fw_root, ignore_errors=True)
        fw_root.mkdir()
        ipa_env = dict(env)
        ipa_env.update({
            "GAME": TITLE_ID, "W": str(work / "ipa"),
            "PATCHED": str(patched), "ROMFS": str(romfs), "MSL_IOS": str(ios),
            "GFXAPI": gfx, "FONT_PY": py,
            "DM_DISPLAY_NAME": display_name, "DM_APP_VERSION": display_version,
            "DM_BUNDLE_ID": f"org.nxnative.{TITLE_ID.lower()}",
            "DM_XCODE_DERIVED_DATA": str(work / "xcode-derived-data"),
            "DM_TEAM_ID": "0000000000", "DM_LANG": language,
            "CONTROL": str(control), "AOC": "", "DM_COPY_ROMFS": "NO",
            "DM_PSO_GPUS": "none", "DM_SHOW_FPS": "YES",
            "DM_FRAMEWORK_ONLY": str(fw_root), "IOS_PULL": "1",
        })
        if icon.is_file():
            ipa_env["DM_ICON"] = str(icon)
        print("[BladesTime] Building Blades of Time framework without RomFS/NSP/keys...")
        run(["bash", str(engine / "dm/ios/tools/build_ipa.sh")], cwd=engine, env=ipa_env)
        framework_name = f"DmGame{TITLE_ID}.framework"
        fw = fw_root / framework_name
        manifest_path = fw / "game.manifest.json"
        if not manifest_path.is_file():
            fail("DM_FRAMEWORK_ONLY failed to generate game.manifest.json")
        manifest = json.loads(manifest_path.read_text())
        exe = manifest.get("framework_executable", "")
        if manifest.get("title_id", "").upper() != TITLE_ID or manifest.get("framework") != framework_name:
            fail("framework identity mismatch")
        for rel in (exe, "profile.tsv", "dm/shader_map.tsv"):
            if not (fw / rel).is_file():
                fail(f"missing framework component {rel}")
        # The framework-only builder removes msl/, but the iOS Shell requires
        # it unless a DMMSLTR1 trailer was appended to the external RomFS.
        # Never declare an IPA successful with only shader_map.tsv.
        if gfx != "nvn":
            fail("Blades of Time must use the NVN backend for this handoff")
        shader_payload = stage_nvn_shader_payload(ios, fw, actual_chain)
        if any(fw.rglob("*.mtl4a")):
            fail("iOS26 IPA must not embed Metal 4 PSO archives")
        if (fw / "pso").is_dir() and any((fw / "pso").iterdir()):
            fail("unexpected Metal PSO archive for --gpu none")
        shell_dir = output / "shell-project"
        shell_dd = output / "shell-derived-data"
        shutil.rmtree(shell_dir, ignore_errors=True)
        shutil.rmtree(shell_dd, ignore_errors=True)
        shell_dir.mkdir()
        shell_env = os.environ.copy()
        shell_env.update({
            "SHELL_DIR": str(shell_dir),
            "DM_SHELL_FRAMEWORKS": str(fw),
            "DM_SHELL_PACKAGE": str(nx / "frontend-ios"),
            "DM_ENGINE_DIR": str(engine),
            "DM_SHELL_NAME": "Blades of Time",
            "DM_BUNDLE_ID": "org.nxnative.bladestime.blades",
            "DM_APP_VERSION": display_version, "DM_TEAM_ID": "0000000000",
            "DM_XCODE_DERIVED_DATA": str(shell_dd), "FONT_PY": py,
            "STD_FONT": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        })
        if prepared.get("provisional"):
            shell_env["DM_GAMES_DIR"] = str(work / "profile")
            shell_env["DM_GAMES_FIRST"] = "1"
        run(["bash", str(shell_script), "--build"], cwd=nx, env=shell_env)
        app = shell_dd / "Build" / "Products" / "Release-iphoneos" / "DmShell.app"
        if not (app / "DmShell").is_file():
            fail("Shell app missing")
        ent = shell_dir / "Gen" / "DmShell.entitlements"
        if not ent.is_file():
            fail("iOS memory entitlement file missing")
        installed = sorted((app / "Frameworks").glob("*.framework"))
        if not any(x.name == framework_name for x in installed):
            fail("Blades of Time framework not embedded in shell")
        bundled_shader = app / "Frameworks" / framework_name / shader_payload["path"]
        if not bundled_shader.is_file() or bundled_shader.stat().st_size != shader_payload["bytes"]:
            fail(f"Xcode dropped the NVN Metal shader image: {bundled_shader}")
        for f in installed:
            run(["xattr", "-cr", str(f)])
            run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(f)])
        run(["xattr", "-cr", str(app)])
        run(["codesign", "--force", "--sign", "-", "--entitlements", str(ent),
             "--timestamp=none", str(app)])
        run(["codesign", "--verify", "--deep", "--strict", str(app)])
        ipa = output / "BladesTime-BoTime.ipa"
        run([py, str(engine / "dm/ios/tools/pack_ipa.py"), str(ipa), "--no-reuse",
             f"Payload/DmShell.app={app}"], cwd=engine)
        with zipfile.ZipFile(ipa) as archive:
            paths = archive.namelist()
            must = ["Payload/DmShell.app/DmShell",
                    f"Payload/DmShell.app/Frameworks/{framework_name}/{exe}"]
            if not all(x in paths for x in must):
                fail("IPA missing app or framework executable")
            shader_entry = f"Payload/DmShell.app/Frameworks/{framework_name}/{shader_payload['path']}"
            if shader_entry not in paths:
                fail(f"IPA missing mandatory iOS game shader image: {shader_entry}")
            if archive.getinfo(shader_entry).file_size != shader_payload["bytes"]:
                fail("shaders in the IPA were truncated")
            shader_checksum = hashlib.sha256()
            with archive.open(shader_entry) as compiled:
                for chunk in iter(lambda: compiled.read(1024 * 1024), b""):
                    shader_checksum.update(chunk)
            if shader_checksum.hexdigest() != shader_payload["sha256"]:
                fail("shaders embedded in IPA differ from validated Metal libraries")
            prohibited = [x for x in paths if x.lower().endswith((".nsp", "/prod.keys",
                 "/romfs.img", ".mtl4a")) or "/aoc/" in x.lower()]
            if prohibited:
                fail(f"IPA contains prohibited game data: {prohibited[:5]}")
        report = {
            "project": "BladesTime", "game": display_name, "title_id": TITLE_ID,
            "package_version": prepared["package_version"], "engine_pin": ENGINE_PIN,
            "graphics": gfx, "provisional_profile": prep["provisional"],
            "shader_chain": actual_chain, "framework": framework_name,
            "shader_payload": {
                "ipa_path": f"Frameworks/{framework_name}/{shader_payload['path']}",
                "size_bytes": shader_payload["bytes"],
                "sha256": shader_payload["sha256"],
                "verified_in_ipa": True,
            },
            "ipa": ipa.name, "ipa_size_bytes": ipa.stat().st_size,
            "ios_deployment_target": "26.0",
            "romfs_in_ipa": False, "dlc_count": 0, "update_count": 1,
            "external_romfs": prepared["game_data"]["folder_url"],
            "signature": "ad-hoc: sideload resign required",
            "limitations": prep.get("limitations", []),
        }
        (output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        try:
            builder.PROG.close(ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
