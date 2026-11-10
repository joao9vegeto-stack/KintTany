#!/usr/bin/env python3
"""Finish the pinned Route C build on macOS from Colab-prepared NXNative artifacts.

This intentionally does NOT call builder.main(): main() scans NSPs, decrypts packages,
extracts RomFS/DLC, rewrites modules and splits shaders. Those are Colab/Linux stages.
The macOS stage reuses the recorded split key, compiles iOS Metal libraries, invokes
build_ipa.sh with DM_FRAMEWORK_ONLY, then builds the Shared Shell.
"""
from __future__ import annotations

import argparse
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

TITLE_ID = "01007EF00011E000"
PACKAGE_VERSION = "v1114112"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"


def fail(message: str) -> None:
    raise SystemExit("[Link2iOS] ERROR: " + message)


def run(command, cwd=None, env=None) -> None:
    command = list(map(str, command))
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def patch_botw_handheld_profile(engine: Path) -> None:
    """Use BOTW's handheld render path as Link2iOS's default while preserving 60 FPS."""
    path = engine / "dm" / "games" / TITLE_ID / "game.tsv"
    if not path.is_file():
        fail(f"pinned BOTW profile is missing: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    fps_rows = [i for i, line in enumerate(lines) if line.split("\t", 1)[0] == "fps_target"]
    if len(fps_rows) != 1 or lines[fps_rows[0]].split("\t") != ["fps_target", "60"]:
        fail("BOTW profile must have exactly one fps_target=60 row; refusing an unexpected profile.")
    op_rows = [i for i, line in enumerate(lines) if line.split("\t", 1)[0] == "op_mode"]
    if len(op_rows) > 1:
        fail("BOTW profile has duplicate op_mode rows.")
    if op_rows:
        fields = lines[op_rows[0]].split("\t")
        if len(fields) != 2 or fields[1] not in ("console", "handheld"):
            fail("BOTW profile has an unexpected op_mode value.")
        lines[op_rows[0]] = "op_mode\thandheld"
    else:
        lines.insert(fps_rows[0] + 1, "op_mode\thandheld")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("[Link2iOS] BOTW defaults: handheld 1280x720, fps_target=60; adaptive frame-step protection remains enabled.")


def patch_shell_icon_pipeline(engine: Path) -> None:
    """Compile BOTW's NACP game icon as the Shared Shell's Home Screen AppIcon."""
    project = engine / "dm" / "ios" / "project-shell.yml"
    script = engine / "dm" / "ios" / "tools" / "build_shell.sh"
    if not project.is_file() or not script.is_file():
        fail("pinned NX2Apple Route C shell sources are missing; cannot customize the BOTW app icon.")
    project_text = project.read_text(encoding="utf-8")
    icon_line = "      - path: ${DM_SHELL_PACKAGE}/AppIcon.icon"
    if icon_line in project_text:
        rows = project_text.splitlines()
        rows = [row for row in rows if not row.startswith(icon_line)]
        project.write_text("\n".join(rows) + "\n", encoding="utf-8")
    elif "AppIcon.icon" in project_text:
        fail("Shared Shell AppIcon resource line differs from the pinned template; refusing an unsafe icon edit.")
    script_text = script.read_text(encoding="utf-8")
    marker = "# Link2iOS BOTW icon asset injection"
    if marker in script_text:
        return
    anchor = next((line for line in script_text.splitlines()
                   if line.startswith("mkdir -p Gen/Assets.xcassets && printf ")), None)
    if anchor is None:
        fail("build_shell.sh no longer creates Gen/Assets.xcassets at the expected point.")
    injection = r'''
# Link2iOS BOTW icon asset injection
if [ -n "${DM_SHELL_ICON_SOURCE:-}" ]; then
  [ -f "$DM_SHELL_ICON_SOURCE" ] || die "BOTW game icon is missing: $DM_SHELL_ICON_SOURCE"
  dims=$(sips -g pixelWidth -g pixelHeight "$DM_SHELL_ICON_SOURCE" 2>/dev/null | awk '/pixelWidth/{w=$2}/pixelHeight/{h=$2}END{print w, h}')
  set -- $dims
  [ "$#" -eq 2 ] && [ "$1" = "$2" ] || die "BOTW NACP icon must be square, got: $dims"
  mkdir -p Gen/Assets.xcassets/AppIcon.appiconset || die "BOTW AppIcon asset set"
  sips -s format png -z 1024 1024 "$DM_SHELL_ICON_SOURCE" --out Gen/Assets.xcassets/AppIcon.appiconset/AppIcon.png >/dev/null || die "convert BOTW game icon"
  printf '%s\n' '{"images":[{"filename":"AppIcon.png","idiom":"universal","platform":"ios","size":"1024x1024"}],"info":{"author":"xcode","version":1}}' > Gen/Assets.xcassets/AppIcon.appiconset/Contents.json || die "BOTW AppIcon manifest"
  t "Link2iOS: Shared Shell AppIcon uses the BOTW NACP game icon"
fi
'''.strip();
    script_text = script_text.replace(anchor, anchor + "\n" + injection)
    script.write_text(script_text, encoding="utf-8")
    print("[Link2iOS] Shared Shell template now compiles the BOTW icon as AppIcon; generic NX2Apple icon resource removed.")


def load_builder(engine: Path):
    for path in (engine / "dm/tools", engine / "dm/games", engine / "dm/gfx/tools", engine / "scripts"):
        sys.path.insert(0, str(path))
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    spec = importlib.util.spec_from_file_location("link2ios_nxnative_builder", script)
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


def validate_workspace(prepared: dict, work: Path, nx: Path, builder, game_profiles):
    if prepared.get("project") != "Link2iOS":
        fail("prepared input does not belong to Link2iOS.")
    if prepared.get("title_id") != TITLE_ID or prepared.get("package_version") != PACKAGE_VERSION:
        fail("only BOTW 1.9.0 / v1114112 is accepted.")
    if prepared.get("nx2apple_tag") != NX2APPLE_TAG:
        fail("unexpected NX2Apple tag.")
    pin = (nx / ".upstream-ref").read_text(encoding="utf-8").strip()
    if pin != ENGINE_PIN or prepared.get("engine_pin") != pin:
        fail("NX2Apple/NXNative pin mismatch; refusing a mixed build.")

    prep_path = work / "link2ios-linux-prep.json"
    if not prep_path.is_file():
        fail("Colab's link2ios-linux-prep.json is missing.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    for key in ("project", "title_id", "package_version", "nx2apple_tag", "engine_pin",
                "shader_package_key", "shader_chain", "modules", "romfs_relative_path", "romfs_id_relative_path"):
        if prep.get(key) != prepared.get(key):
            fail(f"macOS handoff and Colab workspace disagree on {key}.")
    if prep.get("title_id") != TITLE_ID or prep.get("package_version") != PACKAGE_VERSION:
        fail("Colab workspace is not BOTW 1.9.0.")
    shader_key = prep.get("shader_package_key")
    if not isinstance(shader_key, str) or not re.fullmatch(r"[0-9a-f]{64}", shader_key):
        fail("Colab did not provide a valid shader package key.")
    if builder.package_key(work / "shader" / "pkg") != shader_key:
        fail("Colab shader package content differs from the recorded shader-package key.")

    profile = game_profiles.by_title(int(TITLE_ID, 16))
    if profile is None or profile.get("package") != PACKAGE_VERSION:
        fail("pinned NXNative does not expose the BOTW 1.9.0 profile.")
    if profile.get("op_mode") != "handheld":
        fail("Link2iOS BOTW profile default did not resolve to handheld.")
    if str(profile.get("fps_target")) != "60":
        fail("Link2iOS BOTW profile lost its 60 FPS target.")
    version_dir = work / "extract" / PACKAGE_VERSION
    exefs = version_dir / "ExeFS"
    romfs = version_dir / "RomFS.img"
    romfs_id = version_dir / "RomFS.img.id"
    patched = work / f"patched_{PACKAGE_VERSION}"
    shader_pkg = work / "shader" / "pkg"
    aoc_dir = work / "aoc"
    expected_modules = profile.modules_in(exefs)
    if sorted(expected_modules) != sorted(prep.get("modules", [])):
        fail(f"extracted modules differ from the profile: {expected_modules}")
    for path, description in (
        (exefs / "main", "extracted ExeFS/main"),
        (exefs / "main.npdm", "extracted ExeFS/main.npdm"),
        (patched / "main.patched.bin", "rewritten main module"),
        (patched / "main.fixups.tsv", "main fixup table"),
        (romfs, "restored RomFS image"),
        (romfs_id, "RomFS identity sidecar"),
        (shader_pkg, "offline NVN shader package"),
        (aoc_dir, "restored DLC AOC directory"),
    ):
        if not path.exists():
            fail(f"{description} is missing: {path}")
    for name in expected_modules:
        if not (patched / f"{name}.patched.bin").is_file():
            fail(f"rewritten module {name} is missing.")
        if not (patched / f"{name}.fixups.tsv").is_file():
            fail(f"rewriter fixup table for {name} is missing.")
    aoc_images = sorted(aoc_dir.glob("*.img"))
    expected_aoc = {"1.img", "2.img"}
    if {path.name for path in aoc_images} != expected_aoc:
        fail("BOTW framework build requires both AOC images: 1.img and 2.img.")
    if int(prepared.get("aoc_count", -1)) != 2:
        fail("verified Actions handoff does not contain exactly two BOTW AOC images.")
    if set(prepared.get("aoc_images", [])) != expected_aoc:
        fail("Actions AOC image manifest does not match BOTW DLC Pack 1 and Pack 2.")
    if not romfs.is_file() or romfs.stat().st_size != int(prep.get("romfs_size", -1)):
        fail("restored RomFS image size differs from Colab's manifest.")
    try:
        romfs_identity = json.loads(romfs_id.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"NX2Apple RomFS identity sidecar is invalid: {exc}")
    romfs_record = prepared.get("game_data", {}).get("romfs", {})
    if romfs_identity.get("title") != TITLE_ID.lower() or romfs_identity.get("version") != PACKAGE_VERSION:
        fail("RomFS identity sidecar belongs to another game or package version.")
    if romfs_identity.get("bytes") != romfs_record.get("size") or romfs_identity.get("sha256") != romfs_record.get("sha256"):
        fail("RomFS identity sidecar does not match the separately uploaded Drive image.")
    if Path(prepared["romfs_path"]).resolve() != romfs.resolve():
        fail("restored RomFS path differs from the build workspace.")
    if Path(prepared["romfs_id_path"]).resolve() != romfs_id.resolve():
        fail("RomFS identity sidecar path differs from the build workspace.")
    if prepared.get("shader_chain") != prep.get("shader_chain"):
        fail("shader chain mismatch.")
    return profile, version_dir, romfs, aoc_dir, patched, prep


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--prepared-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        fail("the Route C Shared Shell finalizer must run on macOS.")

    nx = args.nx2apple_root.resolve()
    prepared = json.loads(args.prepared_json.read_text(encoding="utf-8"))
    work = Path(prepared["work_dir"]).resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    engine = nx / "engine"
    # Build-local customizations to the pinned checkout; no shared upstream source is committed.
    patch_botw_handheld_profile(engine)
    patch_shell_icon_pipeline(engine)
    builder, game_profiles, nacp, pg = load_builder(engine)
    profile, version_dir, romfs, aoc_dir, patched, prep = validate_workspace(
        prepared, work, nx, builder, game_profiles
    )
    # validate_workspace verifies that both BOTW AOC images exist. Rebind the
    # list in main's scope because the build report below records their names.
    aoc_images = sorted(aoc_dir.glob("*.img"))
    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(parents=True, exist_ok=True)
    (work / "ipa").mkdir(parents=True, exist_ok=True)

    py = sys.executable
    env = builder.tool_env()
    env.setdefault("USER", os.environ.get("USER") or "runner")
    builder.configure_dotnet(env)
    env.update({
        "DM_GAME": TITLE_ID,
        "DM_ROOT": str(work),
        "WORK": str(work / "tmp"),
        "IOS_PULL": "1",
    })
    xlate = engine / "dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate"
    builder.PROG.mode = "lines"
    builder.PROG.plan(4)

    try:
        print("[Link2iOS] Validating the pinned Xcode/iOS SDK, shader translator and Metal compiler...")
        builder.check_prereqs(env, xlate, mac=False)
        builder.check_metal(py, engine, env)

        # A Route C build must use the same translation chain as the Colab shader split.
        expected_chain = prepared["shader_chain"]
        builder.chain_header(py, engine, env, logs)
        actual_chain = builder.chain_of(engine)
        if actual_chain != expected_chain:
            fail(f"shader-chain drift: Colab used {expected_chain}, macOS resolves {actual_chain}.")

        romfs_source = builder.rfs.source(version_dir)
        modules = profile.modules_in(version_dir / "ExeFS")
        facts = pg.build_sources(version_dir / "ExeFS", romfs_source, modules)
        if facts["graphics"][0] != "nvn":
            fail(f"BOTW profile expected NVN, detected {facts['graphics'][0]}.")
        for flag in ("glslc_capture", "vk_capture", "gl_capture", "ue_decode", "oodle_packs", "ue_legacy"):
            if facts.get(flag, (False, ""))[0]:
                fail(f"BOTW unexpectedly requires {flag}; refusing to invent Mac-host capture/decode output.")

        print("[Link2iOS] Reusing Colab's exact NVN split key; compiling only the iOS Metal libraries on macOS...")
        gpu_selection = builder.ios_gpus("none", profile)
        pull = builder.ios_wants_pulling(profile, gpu_selection, False, env)
        if not pull:
            fail("the iOS shader build would omit pulling libraries required by BOTW's Metal 4 path.")
        ios_msl = builder.build_shaders(
            py, engine, work / "shader", xlate, env, logs, profile,
            pkg_key=prepared["shader_package_key"], mac=False, seen=None, pull=pull,
        )
        chain_lib = ios_msl / f"b-{actual_chain}"
        if not (chain_lib.is_dir() or Path(str(chain_lib) + ".img").is_file()):
            fail(f"iOS Metal shader library was not produced: {chain_lib}(.img)")

        control = builder.languages_control(version_dir)
        display_name = nacp.name(control) or profile.get("name") or "The Legend of Zelda: Breath of the Wild"
        display_version = nacp.version(version_dir / "control.nacp") or "1.9.0"
        language = builder.game_language("en-US", False, nacp.languages(control))
        icon = version_dir / "icon.jpg"
        if not icon.is_file():
            fail(f"BOTW NACP icon is missing; cannot build the requested game-specific app icon: {icon}")

        framework_root = output / "frameworks"
        shutil.rmtree(framework_root, ignore_errors=True)
        framework_root.mkdir(parents=True)
        # Keep the Route C framework slim. The two validated BOTW AOC images are
        # external game data in Drive and are selected later through the Shared
        # Shell's Game data folder (EngineLaunchPlan points DM_AOC_DIR to dataURL/aoc).
        # Passing AOC here would make build_ipa.sh copy aoc/ into the framework
        # even with DM_COPY_ROMFS=NO; deliberately pass an empty AOC.
        ipa_env = dict(env)
        ipa_env.update({
            "GAME": TITLE_ID,
            "W": str(work / "ipa"),
            "PATCHED": str(patched),
            "ROMFS": str(romfs),
            "MSL_IOS": str(ios_msl),
            "GFXAPI": "nvn",
            "FONT_PY": py,
            "DM_DISPLAY_NAME": display_name,
            "DM_APP_VERSION": display_version,
            "DM_BUNDLE_ID": f"org.nxnative.{TITLE_ID.lower()}",
            "DM_XCODE_DERIVED_DATA": str(work / "xcode-derived-data"),
            "DM_TEAM_ID": "0000000000",
            "DM_LANG": language,
            "CONTROL": str(control),
            "AOC": "",
            "DM_COPY_ROMFS": "NO",
            "DM_PSO_GPUS": "none",
            "DM_SHOW_FPS": "1",
            "DM_FRAMEWORK_ONLY": str(framework_root),
            "IOS_PULL": "1",
        })
        if icon:
            ipa_env["DM_ICON"] = str(icon)

        print("[Link2iOS] Calling NX2Apple Route C DM_FRAMEWORK_ONLY (no second NSP scan/extraction)...")
        run(["bash", str(engine / "dm/ios/tools/build_ipa.sh")], cwd=engine, env=ipa_env)

        framework_name = f"DmGame{TITLE_ID}.framework"
        framework = framework_root / framework_name
        manifest_path = framework / "game.manifest.json"
        if not manifest_path.is_file():
            fail(f"Route C did not create {manifest_path}.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        executable_name = manifest.get("framework_executable", "")
        if str(manifest.get("title_id", "")).upper() != TITLE_ID:
            fail("framework manifest title ID is not BOTW.")
        if manifest.get("framework") != framework_name or executable_name != framework_name.removesuffix(".framework"):
            fail("framework manifest name/executable does not match the Route C title ID.")
        if manifest.get("chain") != f"b-{actual_chain}":
            fail("framework manifest shader chain differs from the Colab-prepared chain.")
        if not (framework / executable_name).is_file():
            fail("BOTW game framework executable is missing.")
        if not (framework / "profile.tsv").is_file() or not (framework / "dm" / "shader_map.tsv").is_file():
            fail("framework is missing Route C profile or shader tables.")
        if not ((framework / "msl" / f"b-{actual_chain}.img").is_file()
                or (framework / "msl" / f"b-{actual_chain}").is_dir()):
            fail("framework does not contain the packed BOTW iOS Metal shader library.")
        if any(framework.rglob("*.mtl4a")):
            fail("iOS 26 framework unexpectedly contains a Metal 4 PSO archive (.mtl4a).")
        if (framework / "pso").exists() and any((framework / "pso").iterdir()):
            fail("DM_PSO_GPUS=none should leave the framework without an offline PSO archive.")

        shell_dir = output / "shell-project"
        shell_derived_data = output / "shell-derived-data"
        shutil.rmtree(shell_dir, ignore_errors=True)
        shutil.rmtree(shell_derived_data, ignore_errors=True)
        shell_dir.mkdir(parents=True)
        shell_env = os.environ.copy()
        shell_env.update({
            "SHELL_DIR": str(shell_dir),
            "DM_SHELL_FRAMEWORKS": str(framework),
            "DM_SHELL_PACKAGE": str(nx / "frontend-ios"),
            "DM_SHELL_NAME": "Link2iOS",
            "DM_BUNDLE_ID": "org.nxnative.link2ios",
            "DM_APP_VERSION": "1.0.0",
            "DM_TEAM_ID": "0000000000",
            "DM_XCODE_DERIVED_DATA": str(shell_derived_data),
            "FONT_PY": py,
            "STD_FONT": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "DM_SHELL_ICON_SOURCE": str(icon),
        })
        print("[Link2iOS] Building the NX2Apple Shared Shell around the prepared BOTW framework...")
        run(["bash", str(engine / "dm/ios/tools/build_shell.sh"), "--build"], cwd=engine, env=shell_env)

        app = shell_derived_data / "Build" / "Products" / "Release-iphoneos" / "DmShell.app"
        if not (app / "DmShell").is_file():
            fail(f"Shared Shell app was not built: {app}")
        if not (app / "Assets.car").is_file():
            fail("Shared Shell did not compile the BOTW AppIcon asset catalog (Assets.car is missing).")
        if not (shell_dir / "Gen" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon.png").is_file():
            fail("Shared Shell project did not stage the BOTW AppIcon PNG.")
        shell_info = plistlib.loads((app / "Info.plist").read_bytes())
        primary_icon = shell_info.get("CFBundleIcons", {}).get("CFBundlePrimaryIcon", {})
        if primary_icon.get("CFBundleIconName") != "AppIcon":
            fail("Shared Shell Info.plist does not point to the custom BOTW AppIcon.")
        entitlements = shell_dir / "Gen" / "DmShell.entitlements"
        if not entitlements.is_file():
            fail("build_shell.sh did not generate DmShell.entitlements.")

        # A framework cannot carry entitlements; sign it first. Increased Memory Limit belongs to DmShell.
        embedded_frameworks = sorted((app / "Frameworks").glob("*.framework"))
        if not embedded_frameworks:
            fail("Shared Shell does not embed any game framework.")
        if not any(item.name == framework_name for item in embedded_frameworks):
            fail(f"Shared Shell did not embed {framework_name}.")
        for item in embedded_frameworks:
            run(["xattr", "-cr", str(item)])
            run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(item)])
            run(["codesign", "--verify", "--strict", str(item)])
        run(["xattr", "-cr", str(app)])
        run(["codesign", "--force", "--sign", "-", "--entitlements", str(entitlements),
             "--timestamp=none", str(app)])
        run(["codesign", "--verify", "--deep", "--strict", str(app)])
        entitlement_check = subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", str(app / "DmShell")],
            capture_output=True, text=True, check=False,
        )
        if "com.apple.developer.kernel.increased-memory-limit" not in (
            entitlement_check.stdout + entitlement_check.stderr
        ):
            fail("ad-hoc signature is missing Increased Memory Limit.")

        ipa = output / "Link2iOS-BOTW.ipa"
        packer = engine / "dm/ios/tools/pack_ipa.py"
        run([py, str(packer), str(ipa), "--no-reuse",
             f"Payload/DmShell.app={app}"], cwd=engine)
        with zipfile.ZipFile(ipa) as archive:
            entries = archive.namelist()
            required = [
                "Payload/DmShell.app/DmShell",
                f"Payload/DmShell.app/Frameworks/{framework_name}/{executable_name}",
                f"Payload/DmShell.app/Frameworks/{framework_name}/game.manifest.json",
            ]
            missing = [name for name in required if name not in entries]
            if missing:
                fail("final IPA is missing Route C components: " + ", ".join(missing))
            prohibited = [
                name for name in entries
                if name.lower().endswith("/romfs.img")
                or "/aoc/" in name.lower()
                or name.lower().endswith(".nsp")
                or name.lower().endswith("/prod.keys")
                or name.lower().endswith(".mtl4a")
            ]
            if prohibited:
                fail("IPA unexpectedly contains game data, keys or an iOS 27 PSO: " + ", ".join(prohibited[:20]))

        report = {
            "project": "Link2iOS",
            "game": "The Legend of Zelda: Breath of the Wild",
            "title_id": TITLE_ID,
            "display_version": display_version,
            "package_version": PACKAGE_VERSION,
            "nx2apple_tag": NX2APPLE_TAG,
            "engine_pin": ENGINE_PIN,
            "shader_chain": actual_chain,
            "shader_package_key": prepared["shader_package_key"],
            "framework": framework_name,
            "ipa": ipa.name,
            "ipa_size_bytes": ipa.stat().st_size,
            "build_architecture": {
                "colab_linux": [
                    "NXNative build_ipa_from_nsp.py content-meta scan",
                    "XCI base + update v1114112 extraction into merged RomFS.img",
                    "DLC title 01007EF00011F001 extraction into aoc/1.img",
                    "DLC title 01007EF00011F002 extraction into aoc/2.img",
                    "AArch64 module rewrite", "NVN offline shader split",
                ],
                "macos": ["iOS Metal library compilation", "DM_FRAMEWORK_ONLY Route C framework",
                          "build_shell Shared Shell", "ad-hoc signing and IPA packaging"],
                "mac_downloaded_original_nsp": False,
                "mac_downloaded_prod_keys": False,
                "mac_repeated_nsp_extraction": False,
                "mac_repeated_shader_split": False,
            },
            "ipa_contains_romfs": False,
            "ipa_contains_aoc": False,
            "ipa_contains_nsp": False,
            "ipa_contains_prod_keys": False,
            "external_game_data": {
                "drive_folder_url": prepared["game_data"]["folder_url"],
                "romfs_size_bytes": prepared["game_data"]["romfs"]["size"],
                "aoc_images": sorted(path.name for path in aoc_images),
                "aoc_title_ids": {
                    "1.img": "01007EF00011F001",
                    "2.img": "01007EF00011F002",
                },
                "layout": f"games/{TITLE_ID}/romfs.img + games/{TITLE_ID}/aoc/",
            },
            "pipeline_archive": {
                "included": False,
                "gpu": "none",
                "reason": "iOS 26 target: ordinary Metal shader libraries are embedded; no .mtl4a archive is copied, so the device prepares pipeline bases on first use.",
            },
            "signature": "ad-hoc; sideloading re-sign is required",
            "entitlement": "com.apple.developer.kernel.increased-memory-limit",
            "runtime_defaults": {
                "op_mode": "handheld",
                "resolution_mode": "1280x720 before DM_RENDER_SCALE",
                "fps_target": 60,
                "adaptive_frame_step": "enabled; frames may step down if the GPU misses 60 FPS deadlines",
            },
            "home_screen_icon": "BOTW NACP icon.jpg compiled into DmShell.app/Assets.car as AppIcon",
        }
        (output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"[Link2iOS] IPA complete: {ipa} ({ipa.stat().st_size:,} bytes)")
    finally:
        try:
            builder.PROG.close(ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
