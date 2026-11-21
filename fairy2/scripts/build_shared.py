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

TITLE_ID = "0100B9801F872000"
NX2APPLE_REF = "Fairy2iOS"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"


def fail(message: str) -> None:
    raise SystemExit("[Fairy2iOS] ERROR: " + message)


def run(command, cwd=None, env=None) -> None:
    command = list(map(str, command))
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def load_builder(engine: Path):
    for path in (engine / "dm/tools", engine / "dm/games", engine / "dm/gfx/tools", engine / "scripts"):
        sys.path.insert(0, str(path))
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    spec = importlib.util.spec_from_file_location("fairy2_nxnative_builder", script)
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
    if d.get("project") != "Fairy2iOS" or d.get("title_id") != TITLE_ID:
        fail("wrong prepared game")
    if d.get("engine_pin") != ENGINE_PIN or (nx / ".upstream-ref").read_text().strip() != ENGINE_PIN:
        fail("engine pin mismatch")
    prep = json.loads((work / "fairy2-linux-prep.json").read_text())
    for key in ("title_id", "package_version", "engine_pin", "graphics", "shader_chain",
                "shader_package_key", "modules", "provisional", "shader_split_stage",
                "mac_host_stages", "source_capture_flags", "shader_versions",
                "jit_required", "linux_ue_decode_complete"):
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
        if prep["shader_split_stage"] == "linux_complete":
            key = prep.get("shader_package_key") or ""
            if not re.fullmatch(r"[0-9a-f]{64}", key):
                fail("Linux NVN shader key missing")
            if builder.package_key(work / "shader" / "pkg") != key:
                fail("Linux-completed NVN shader package failed checksum verification")
        elif prep["shader_split_stage"] != "mac_pending" or not prep.get("mac_host_stages") or prep.get("shader_package_key") is not None:
            fail("NVN split pending without a real native-host capture dependency")
    aoc_items = prep.get("aoc_images", [])
    if sorted(x["name"] for x in aoc_items) != sorted(
            x.name for x in (work / "aoc").glob("*.img")):
        fail("AOC DLC inventory changed after Colab preparation")
    for item in aoc_items:
        if (work / "aoc" / item["name"]).stat().st_size != int(item["size"]):
            fail("AOC DLC data truncated")
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
    record = {"path": f"msl/{source.name}",
              "bytes": destination.stat().st_size,
              "sha256": digest.hexdigest()}
    result = dict(record, files=[record], library_source=str(source))
    print("[Fairy2iOS] Bundled compiled NVN shaders into framework:", result, flush=True)
    return result


def configure_fairy2_frame_rate_menu(framework: Path) -> None:
    """The real engine FPS target and direct A/B swap, shared with IPA repack."""
    manifest_path = framework / "game.manifest.json"
    if not manifest_path.is_file():
        fail(f"framework manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rel = manifest.get("launcher")
    if manifest.get("title_id", "").upper() != TITLE_ID or rel != "dm/launcher.json":
        fail("Fairy2iOS manifest has unexpected launcher location or identity")
    path = framework / rel
    if not path.is_file():
        fail(f"framework missing launcher settings: {path}")
    helper_file = Path(__file__).resolve().parent / "repack_ipa.py"
    helper_spec = importlib.util.spec_from_file_location("fairy2_repack_settings", helper_file)
    if helper_spec is None or helper_spec.loader is None:
        fail("Fairy Tail 2 repack helper not importable")
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    try:
        data = helper.configure_launcher(json.loads(path.read_text(encoding="utf-8")))
        helper.validate_settings(data)
    except (ValueError, RuntimeError, KeyError) as error:
        fail(str(error))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[Fairy2iOS] DM_FPS_TARGET 30/60 + DM_PAD_MAP A/B swap installed.", flush=True)



def stage_layer_shader_payload(ios: Path, framework: Path, graphics: str) -> dict:
    """Bundle the *actual* Metal shader files for GL/Vulkan titles."""
    if graphics not in ("gl", "vulkan"):
        fail(f"unexpected layer graphics {graphics!r}")
    folder = "gl" if graphics == "gl" else "vk"
    lib = "gl_shaders.metallib" if graphics == "gl" else "vk_shaders.metallib"
    origin = ios / folder
    primary = origin / lib
    if not primary.is_file() or primary.stat().st_size < 32:
        fail(f"{graphics} iOS Metal shader library missing: {primary}")
    target = framework / "msl" / folder
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(origin, target)
    files = []
    for source in sorted(origin.rglob("*")):
        if not source.is_file():
            continue
        suffix = source.relative_to(origin)
        if ".." in suffix.parts or source.suffix.lower() == ".mtl4a":
            fail(f"unsafe shader asset or incompatible Metal 4 archive: {source}")
        dest = target / suffix
        if not dest.is_file() or source.stat().st_size != dest.stat().st_size:
            fail(f"shader data truncated while staging {source}")
        sha = hashlib.sha256()
        with dest.open("rb") as stream:
            for part in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                sha.update(part)
        files.append({"path": f"msl/{folder}/{suffix.as_posix()}",
                      "bytes": dest.stat().st_size, "sha256": sha.hexdigest()})
    main = next((x for x in files if x["path"] == f"msl/{folder}/{lib}"), None)
    if main is None:
        fail(f"Metal library vanished from the staged {graphics} folder")
    return dict(main, files=files, library_source=str(primary))


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
    # The current Fairy2iOS/NX2Apple Shell lives here, NOT in dm/ios/tools/build_shell.sh.
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
        # The Mac runner operates strictly on the Colab-prepared workspace.
        # Only actual native shader captures/decoders run here, and an NVN
        # shader split is reused unless Mac-only capture inputs were needed.
        from mac_capture import complete, finish_jit_if_needed
        package_key, extra_roots = complete(
            builder, engine, version, patched, work, env, logs,
            profile, prep, py, facts)
        if gfx == "nvn":
            builder.check_metal(py, engine, env)
            gpus = builder.ios_gpus("none", profile)
            pulling = builder.ios_wants_pulling(profile, gpus, False, env)
            ios = builder.build_shaders(
                py, engine, work / "shader", xlate, env, logs, profile,
                pkg_key=package_key, mac=False, seen=None, pull=pulling)
            chain_lib = ios / f"b-{actual_chain}"
            if not (chain_lib.is_dir() or Path(str(chain_lib) + ".img").is_file()):
                fail("NVN iOS Metal shader library missing")
        elif gfx == "gl":
            ios = builder.build_gl_shaders(
                py, engine,
                [builder.rfs.source(version), version / "ExeFS/main", *extra_roots],
                work / "shader", env, logs, profile, mac=False,
                provisional=bool(prep["provisional"]),
                fixed=bool(facts.get("gl_fixed", (False, ""))[0]))
        elif gfx == "vulkan":
            # Use NXNative's native Vulkan capture and all source shader inputs;
            # Dagor/Blades of Time hash lists are not relevant to Fairy Tail 2.
            ios = builder.build_vk_shaders(
                py, engine,
                [builder.rfs.source(version), version / "ExeFS/main", *extra_roots],
                work / "shader", env, logs, profile,
                mac=False, provisional=bool(prep["provisional"]))
        else:
            fail(f"unsupported graphics backend: {gfx}")
        # NXNative runs JIT host capture after shader compilation.
        finish_jit_if_needed(builder, engine, version, patched, work, env,
                             logs, profile, prep, py)
        control = builder.languages_control(version)
        display_name = nacp.name(control) or "Fairy Tail 2"
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
        print("[Fairy2iOS] Building Fairy Tail 2 framework without RomFS/NSP/keys...")
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
        configure_fairy2_frame_rate_menu(fw)
        # The framework-only builder removes msl/, but the iOS Shell requires
        # it unless a DMMSLTR1 trailer was appended to the external RomFS.
        # Never declare an IPA successful with only shader_map.tsv.
        shader_payload = (
            stage_nvn_shader_payload(ios, fw, actual_chain) if gfx == "nvn"
            else stage_layer_shader_payload(ios, fw, gfx))
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
            "DM_SHELL_NAME": "Fairy Tail 2",
            "DM_BUNDLE_ID": "org.nxnative.fairy2.0100b9801f872000",
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
            fail("Fairy Tail 2 framework not embedded in shell")
        for item in shader_payload["files"]:
            bundled_shader = app / "Frameworks" / framework_name / item["path"]
            if not bundled_shader.is_file() or bundled_shader.stat().st_size != item["bytes"]:
                fail(f"Xcode dropped a compiled Metal shader asset: {bundled_shader}")
        for f in installed:
            run(["xattr", "-cr", str(f)])
            run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(f)])
        run(["xattr", "-cr", str(app)])
        run(["codesign", "--force", "--sign", "-", "--entitlements", str(ent),
             "--timestamp=none", str(app)])
        run(["codesign", "--verify", "--deep", "--strict", str(app)])
        ipa = output / "Fairy2iOS-FairyTail2.ipa"
        run([py, str(engine / "dm/ios/tools/pack_ipa.py"), str(ipa), "--no-reuse",
             f"Payload/DmShell.app={app}"], cwd=engine)
        with zipfile.ZipFile(ipa) as archive:
            paths = archive.namelist()
            must = ["Payload/DmShell.app/DmShell",
                    f"Payload/DmShell.app/Frameworks/{framework_name}/{exe}",
                    f"Payload/DmShell.app/Frameworks/{framework_name}/dm/launcher.json"]
            if not all(x in paths for x in must):
                fail("IPA missing app or framework executable")
            launcher_entry = f"Payload/DmShell.app/Frameworks/{framework_name}/dm/launcher.json"
            launcher_config = json.loads(archive.read(launcher_entry).decode("utf-8"))
            rate_rows = [row for row in launcher_config.get("settings", []) if row.get("env") == "DM_FPS_TARGET"]
            map_rows = [row for row in launcher_config.get("settings", []) if row.get("env") == "DM_PAD_MAP"]
            if (launcher_config.get("game") != TITLE_ID or len(rate_rows) != 1 or
                    rate_rows[0].get("default") != "30" or
                    [opt[0] for opt in rate_rows[0].get("options", [])] != ["30", "60"] or
                    len(map_rows) != 1 or map_rows[0].get("on") != "A=B,B=A" or
                    any(row.get("env") == "DM_FPS" for row in launcher_config.get("settings", []))):
                fail("signed IPA does not contain runtime target 30/60 and gamepad A/B settings")
            # NVN ships one image, GL/Vulkan ship a resource directory.
            # Verify the exact compiled file bytes inside the signed IPA.
            for item in shader_payload["files"]:
                shader_entry = f"Payload/DmShell.app/Frameworks/{framework_name}/{item['path']}"
                if shader_entry not in paths:
                    fail(f"IPA missing mandatory Metal shader: {shader_entry}")
                if archive.getinfo(shader_entry).file_size != item["bytes"]:
                    fail(f"IPA Metal asset truncated: {shader_entry}")
                shader_hash = hashlib.sha256()
                with archive.open(shader_entry) as compiled:
                    for chunk in iter(lambda: compiled.read(4 * 1024 * 1024), b""):
                        shader_hash.update(chunk)
                if shader_hash.hexdigest() != item["sha256"]:
                    fail(f"IPA shader bytes differ from compiled library: {shader_entry}")
            prohibited = [x for x in paths if x.lower().endswith((".nsp", "/prod.keys",
                 "/romfs.img", ".mtl4a")) or "/aoc/" in x.lower()]
            if prohibited:
                fail(f"IPA contains prohibited game data: {prohibited[:5]}")
        report = {
            "project": "Fairy2iOS", "game": display_name, "title_id": TITLE_ID,
            "package_version": prepared["package_version"], "engine_pin": ENGINE_PIN,
            "graphics": gfx, "provisional_profile": prep["provisional"],
            "shader_chain": actual_chain, "framework": framework_name,
            "shader_payload": {
                "ipa_path": f"Frameworks/{framework_name}/{shader_payload['path']}",
                "size_bytes": shader_payload["bytes"],
                "sha256": shader_payload["sha256"],
                "verified_in_ipa": True,
                "files": shader_payload["files"],
            },
            "linux_shader_split_stage": prep["shader_split_stage"],
            "mac_host_stages": prep["mac_host_stages"],
            "ipa": ipa.name, "ipa_size_bytes": ipa.stat().st_size,
            "ios_deployment_target": "26.0",
            "frame_rate_choice": {"env": "DM_FPS_TARGET", "default": 30, "options": [30, 60],
                                  "game_engine_60fps_unlock_verified": False,
                                  "actual_60_fps_unverified": True},
            "swap_ab_choice": {"env": "DM_PAD_MAP", "off": "", "on": "A=B,B=A"},
            "romfs_in_ipa": False, "dlc_count": 16, "aoc_count": len(prep["aoc_images"]), "update_count": 1,
            "external_romfs": prepared["game_data"]["folder_url"],
            "external_aoc": prepared["game_data"].get("aoc", []),
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
