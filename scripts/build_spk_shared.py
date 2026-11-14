#!/usr/bin/env python3
"""macOS Route C finalizer for Sparking! ZERO: Unreal/Oodle decode -> split -> Metal -> framework -> Shared Shell."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath

TITLE_ID = "010035F022078000"
PROJECT = "SpkIOSzero"
BRANCH = "SpkIOSzero"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
EXPECTED_MAIN_BUILD_ID = "68edafd68c7bc1a1af50b82aac838018"
EXPECTED_MAIN_SHA256 = "a0f8f0644c92384ddb1baac1c21aecbeeace5bc99ad40895e216add61da78efe"

def fail(message: str) -> None: raise SystemExit("[SpkIOSzero] ERROR: " + message)
def run(command, cwd=None, env=None) -> None:
    cmd = list(map(str, command)); print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()

def load_builder(engine: Path):
    for folder in (engine / "dm/tools", engine / "dm/games", engine / "dm/gfx/tools", engine / "scripts"):
        sys.path.insert(0, str(folder))
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    if not script.is_file(): fail(f"Pinned NXNative build script is missing: {script}")
    spec = importlib.util.spec_from_file_location("spk_nxnative_builder", script)
    if spec is None or spec.loader is None: fail("Could not load the pinned NXNative builder.")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    import game as game_profiles
    import nacp
    import profile_guess as pg
    module.gamemod = game_profiles; module.nacp = nacp; module.pg = pg
    return module, game_profiles, nacp, pg

def validate_workspace(prepared: dict, work: Path, nx: Path, builder, game_profiles):
    if prepared.get("project") != PROJECT or prepared.get("branch") != BRANCH:
        fail("Prepared input does not belong to the SpkIOSzero project/branch.")
    if prepared.get("title_id") != TITLE_ID or not prepared.get("package_version"):
        fail("Prepared input title ID/package version is invalid.")
    if prepared.get("nx2apple_tag") != NX2APPLE_TAG or prepared.get("engine_pin") != ENGINE_PIN:
        fail("NX2Apple/NXNative pin mismatch.")
    pin_file = nx / ".upstream-ref"
    if not pin_file.is_file() or pin_file.read_text(encoding="utf-8").strip() != ENGINE_PIN:
        fail("Checked-out NXNative does not match the pinned engine commit.")
    prep_path = work / "spk-ios-zero-linux-prep.json"
    if not prep_path.is_file(): fail("Colab Linux preparation manifest is missing.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    for key in ("project", "title_id", "package_version", "nx2apple_tag", "engine_pin",
                "main_build_id", "main_sha256", "allocator", "modules", "shader_chain",
                "input_package_count", "input_nsp_count", "input_xci_count",
                "input_base_package_type", "input_base_package_name",
                "romfs_relative_path", "romfs_id_relative_path", "aoc_relative_dir",
                "romfs_size", "aoc_images", "graphics_api", "unreal_shader_sources"):
        if prep.get(key) != prepared.get(key): fail(f"Actions handoff and Colab workspace disagree on {key}.")
    if prep.get("main_build_id") != EXPECTED_MAIN_BUILD_ID or prep.get("main_sha256") != EXPECTED_MAIN_SHA256:
        fail("Colab workspace is not the reviewed Sparking! ZERO main build.")
    if prep.get("graphics_api") != "nvn": fail(f"Sparking! ZERO expected NVN; Colab recorded {prep.get('graphics_api')}.")
    base_type = prep.get("input_base_package_type")
    if (prep.get("input_package_count") != 12 or base_type not in ("NSP", "XCI")
        or prep.get("input_base_package_name", "").lower().endswith(".xci") != (base_type == "XCI")
        or prep.get("input_xci_count") != (1 if base_type == "XCI" else 0)):
        fail("Restored Colab manifest does not describe exactly one validated base NSP/XCI plus the update and 10 DLC NSPs.")
    ue_flags = prep.get("unreal_shader_sources") or {}
    if not any(ue_flags.get(k) for k in ("ue_decode", "oodle_packs", "ue_legacy")):
        fail("Colab did not identify Unreal/Oodle shader sources.")
    if builder.chain_of(nx / "engine") != prepared["shader_chain"]:
        fail("NXNative chain header does not match the Colab preparation manifest.")

    version_dir = work / "extract" / prepared["package_version"]
    exefs = version_dir / "ExeFS"
    romfs_rel = PurePosixPath(prep["romfs_relative_path"])
    identity_rel = PurePosixPath(prep["romfs_id_relative_path"])
    if romfs_rel.is_absolute() or ".." in romfs_rel.parts or identity_rel.is_absolute() or ".." in identity_rel.parts:
        fail("Unsafe game-data path in Linux manifest.")
    romfs = work.joinpath(*romfs_rel.parts); romfs_id = work.joinpath(*identity_rel.parts)
    patched = work / f"patched_{prepared['package_version']}"
    profile_root = work / "profile"; profile_dir = profile_root / TITLE_ID
    for path, description in (
        (exefs / "main", "extracted main"), (exefs / "main.npdm", "main.npdm"),
        (patched / "main.patched.bin", "rewritten main"), (patched / "main.fixups.tsv", "main fixups"),
        (patched / "main.cuts.tsv", "main cut audit"), (patched / "main.obs.tsv", "main observation audit"),
        (profile_dir / "game.tsv", "provisional game profile"), (profile_dir / "patches.py", "SpNet profile patch"),
        (romfs, "restored RomFS"), (romfs_id, "RomFS identity sidecar")):
        if not path.is_file(): fail(f"{description} is missing: {path}")
    if builder.build_id(exefs / "main") != EXPECTED_MAIN_BUILD_ID or sha256_file(exefs / "main") != EXPECTED_MAIN_SHA256:
        fail("Extracted main build ID/SHA-256 differs from the reviewed Sparking! ZERO binary.")
    game_data = prepared.get("game_data") or {}; romfs_record = game_data.get("romfs") or {}
    if not romfs_record.get("sha256") or romfs.stat().st_size != int(romfs_record.get("size", -1)):
        fail("External RomFS size differs from the Drive handoff.")
    if sha256_file(romfs) != romfs_record["sha256"]: fail("External RomFS SHA-256 differs from the Drive handoff.")
    try: identity = json.loads(romfs_id.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc: fail(f"Invalid RomFS identity sidecar: {exc}")
    if identity.get("title") != TITLE_ID.lower() or identity.get("version") != prepared["package_version"]:
        fail("RomFS identity sidecar belongs to another title/version.")
    if identity.get("bytes") != romfs_record["size"] or identity.get("sha256") != romfs_record["sha256"]:
        fail("RomFS identity sidecar does not describe the restored RomFS bytes/hash.")
    aoc_dir = work / prep["aoc_relative_dir"]
    aoc_images = sorted(p for p in aoc_dir.glob("*.img") if p.is_file())
    expected_aoc = {x.get("name") for x in prep["aoc_images"]}
    if not aoc_images or {p.name for p in aoc_images} != expected_aoc:
        fail("Restored AOC images differ from the Colab preparation manifest.")
    handoff_aoc = game_data.get("aoc") or []
    if {x.get("name") for x in handoff_aoc} != expected_aoc: fail("AOC Drive handoff and preparation manifest disagree.")
    if int(prepared.get("aoc_count", -1)) != len(aoc_images): fail("Restored AOC image count differs from Actions input.")
    for path in aoc_images:
        rec = next((x for x in handoff_aoc if x.get("name") == path.name), None)
        if not rec or path.stat().st_size != int(rec.get("size", -1)) or sha256_file(path) != rec.get("sha256"):
            fail(f"Restored AOC image hash/size mismatch: {path.name}")
    expected_modules = list(prep["modules"])
    if sorted(expected_modules) != sorted(prepared.get("modules", [])): fail("Colab module list differs from Actions input.")
    for name in expected_modules:
        if not (patched / f"{name}.patched.bin").is_file() or not (patched / f"{name}.fixups.tsv").is_file():
            fail(f"Rewritten module/fixups missing for {name}.")
    cuts = [x for x in (patched / "main.cuts.tsv").read_text(errors="replace").splitlines()
            if x.strip() and not x.lstrip().startswith("#")]
    obs = [x for x in (patched / "main.obs.tsv").read_text(errors="replace").splitlines()
           if x.strip() and not x.lstrip().startswith("#")]
    fixups = (patched / "main.fixups.tsv").read_text(encoding="utf-8")
    if len(cuts) != 2 or not any("0x1e4db30" in x for x in cuts) or not any("0x1b74d70" in x for x in cuts):
        fail("The final rewrite is missing the exact two expected SPK cuts.")
    if len(obs) != 1 or "0x1e4db34" not in obs[0]: fail("The final rewrite is missing the exact x19 allocator observation gate.")
    if "# UE_MALLOC_VT\t0x8703ab8" not in fixups or "# UE_MALLOC_SLOT\t0x17" not in fixups:
        fail("The final rewrite fixups do not identify the UE5_SPK allocator layout.")
    if "0x1b74d70" not in (profile_dir / "patches.py").read_text(encoding="utf-8"):
        fail("The provisional profile does not carry the build-gated SpNet StartupModule patch.")
    profile = game_profiles.load(TITLE_ID)
    if sorted(profile.modules_in(exefs)) != sorted(expected_modules): fail("Loaded provisional profile modules differ from the Colab manifest.")
    return profile, version_dir, romfs, romfs_id, aoc_dir, aoc_images, patched, prep, profile_root

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--prepared-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin": fail("The SpkIOSzero Route C finalizer must run on macOS.")
    nx = args.nx2apple_root.resolve()
    prepared = json.loads(args.prepared_json.read_text(encoding="utf-8"))
    work = Path(prepared["work_dir"]).resolve(); output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    engine = nx / "engine"
    repo_scripts = Path(__file__).resolve().parent; sys.path.insert(0, str(repo_scripts))
    import spk_engine
    spk_engine.patch(engine)
    profile_root = work / "profile"
    os.environ["DM_GAMES_DIR"] = str(profile_root); os.environ["DM_GAMES_FIRST"] = "1"; os.environ["DM_GAME"] = TITLE_ID
    builder, game_profiles, nacp, pg = load_builder(engine)
    profile, version_dir, romfs, romfs_id, aoc_dir, aoc_images, patched, prep, _ = validate_workspace(
        prepared, work, nx, builder, game_profiles)
    logs = work / "logs"; logs.mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(parents=True, exist_ok=True); (work / "ipa").mkdir(parents=True, exist_ok=True)

    py = sys.executable
    env = builder.tool_env(); env.setdefault("USER", os.environ.get("USER") or "runner")
    env.update({"DM_GAME": TITLE_ID, "DM_GAMES_DIR": str(profile_root), "DM_GAMES_FIRST": "1",
                "DM_ROOT": str(work), "WORK": str(work / "tmp"), "IOS_PULL": "1"})
    builder.configure_dotnet(env)
    xlate = engine / "dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate"
    builder.PROG.mode = "lines"; builder.PROG.plan(6)
    try:
        print("[SpkIOSzero] Checking pinned Xcode/iOS SDK, shader translator and Metal toolchain...", flush=True)
        builder.check_prereqs(env, xlate, mac=False); builder.check_metal(py, engine, env)
        builder.chain_header(py, engine, env, logs)
        actual_chain = builder.chain_of(engine)
        if actual_chain != prepared["shader_chain"]:
            fail(f"Shader-chain drift: Colab used {prepared['shader_chain']}, macOS resolves {actual_chain}.")

        romfs_source = builder.rfs.source(version_dir); modules = profile.modules_in(version_dir / "ExeFS")
        facts = pg.build_sources(version_dir / "ExeFS", romfs_source, modules)
        if facts["graphics"][0] != "nvn": fail(f"Sparking! ZERO expected NVN; NXNative detected {facts['graphics'][0]}.")
        for key in ("ue_decode", "oodle_packs", "ue_legacy"):
            expected = bool(prep["unreal_shader_sources"].get(key)); actual = bool(facts.get(key, (False, ""))[0])
            if expected != actual: fail(f"Unreal shader-source detection changed between Colab and macOS for {key}: {expected} != {actual}.")
        if not any(facts.get(key, (False, ""))[0] for key in ("ue_decode", "oodle_packs", "ue_legacy")):
            fail("Pinned macOS checkout no longer detects this game's Unreal/Oodle shader inputs.")

        if facts.get("ue_decode", (False, ""))[0]:
            print("[SpkIOSzero] Running NXNative Unreal shader extraction and game-owned Oodle decode on macOS...", flush=True)
            builder.decode_ue_shaders(engine, {prepared["package_version"]: version_dir},
                prepared["package_version"], patched, work, env, logs, profile)
            ue_dir = version_dir / "ue_shaders"
            decoded = sorted(ue_dir.glob("*.ushaderbytecode")) if ue_dir.is_dir() else []
            if not decoded: fail("The macOS Unreal/Oodle stage produced no decoded .ushaderbytecode files.")
        else:
            print("[SpkIOSzero] UE shader archives need no separate decode_ue_shaders stage; Oodle-backed split will run in the Mac host.", flush=True)
        oodle = None
        if facts.get("oodle_packs", (False, ""))[0] or facts.get("ue_legacy", (False, ""))[0]:
            oodle = lambda: {
                "DM_OODLE_HOST": str(builder.build_mac_host(engine, work / "tools" / "dmhost", env, logs, profile)),
                "DM_OODLE_MODULES": str(patched),
            }
        print("[SpkIOSzero] Splitting decoded Unreal shaders on macOS with exact rewritten main, RomFS, profile and DLC AOC inputs...", flush=True)
        shader_package = work / "shader" / "pkg"
        package_key = builder.split_shaders(py, engine, [romfs_source], [version_dir / "ExeFS" / "main"],
            shader_package, env, logs, profile, provisional=True, oodle=oodle, dlc_roms=aoc_images)
        if not isinstance(package_key, str) or not re.fullmatch(r"[0-9a-f]{64}", package_key):
            fail("NXNative shader splitter did not produce a valid package content key.")
        if builder.package_key(shader_package) != package_key: fail("Shader package content key does not match the split result.")

        gpu_selection = builder.ios_gpus("none", profile)
        pull = builder.ios_wants_pulling(profile, gpu_selection, False, env)
        print(f"[SpkIOSzero] Compiling iOS Metal libraries (pulling libraries: {'yes' if pull else 'no'})...", flush=True)
        ios_msl = builder.build_shaders(py, engine, work / "shader", xlate, env, logs, profile,
            pkg_key=package_key, mac=False, seen=None, pull=pull)
        chain_lib = ios_msl / f"b-{actual_chain}"
        if not (chain_lib.is_dir() or Path(str(chain_lib) + ".img").is_file()):
            fail(f"iOS Metal shader libraries are missing: {chain_lib}(.img)")
        if not (shader_package.is_dir() and any(shader_package.rglob("shader_map.tsv"))):
            fail("The shader split did not produce shader_map.tsv.")
        if not (Path(str(chain_lib) + ".img").is_file() or (chain_lib / "inputs.tsv").is_file()):
            fail("The iOS Metal shader output does not contain a full-build library/stamp.")

        control = builder.languages_control(version_dir)
        display_name = nacp.name(control) or profile.get("name") or "DRAGON BALL: Sparking! ZERO"
        display_version = nacp.version(version_dir / "control.nacp") or "1.0.0"
        language = builder.game_language("en-US", False, nacp.languages(control))
        framework_root = output / "frameworks"; shutil.rmtree(framework_root, ignore_errors=True); framework_root.mkdir(parents=True)
        ipa_env = dict(env)
        ipa_env.update({"GAME": TITLE_ID, "W": str(work / "ipa"), "PATCHED": str(patched),
            "ROMFS": str(romfs), "MSL_IOS": str(ios_msl), "GFXAPI": "nvn", "FONT_PY": py,
            "DM_DISPLAY_NAME": display_name, "DM_APP_VERSION": display_version,
            "DM_BUNDLE_ID": f"org.nxnative.{TITLE_ID.lower()}",
            "DM_XCODE_DERIVED_DATA": str(work / "xcode-derived-data"), "DM_TEAM_ID": "0000000000",
            "DM_LANG": language, "CONTROL": str(control), "AOC": "", "DM_COPY_ROMFS": "NO",
            "DM_PSO_GPUS": "none", "DM_SHOW_FPS": "1", "DM_FRAMEWORK_ONLY": str(framework_root), "IOS_PULL": "1"})
        print("[SpkIOSzero] Building NX2Apple DM_FRAMEWORK_ONLY game framework; RomFS and DLC remain external.", flush=True)
        run(["bash", str(engine / "dm/ios/tools/build_ipa.sh")], cwd=engine, env=ipa_env)

        framework_name = f"DmGame{TITLE_ID}.framework"; framework = framework_root / framework_name
        manifest_path = framework / "game.manifest.json"
        if not manifest_path.is_file(): fail(f"NX2Apple did not create {manifest_path}.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); executable_name = manifest.get("framework_executable", "")
        if str(manifest.get("title_id", "")).upper() != TITLE_ID: fail("Framework manifest title ID is not Sparking! ZERO.")
        if manifest.get("framework") != framework_name or executable_name != framework_name.removesuffix(".framework"):
            fail("Framework manifest name/executable does not match the Sparking! ZERO title ID.")
        if manifest.get("chain") != f"b-{actual_chain}": fail("Framework manifest shader chain differs from macOS Metal build.")
        for rel in (executable_name, "profile.tsv", "dm/shader_map.tsv"):
            if not (framework / rel).is_file(): fail(f"Framework is missing {rel}.")
        if not ((framework / "msl" / f"b-{actual_chain}.img").is_file()
                or (framework / "msl" / f"b-{actual_chain}").is_dir()):
            fail("Framework does not contain the iOS Metal shader library.")
        if any(framework.rglob("*.mtl4a")): fail("iOS framework unexpectedly contains an unsupported .mtl4a PSO archive.")
        if (framework / "pso").exists() and any((framework / "pso").iterdir()):
            fail("DM_PSO_GPUS=none should leave the framework without an offline PSO archive.")

        shell_dir = output / "shell-project"; shell_dd = output / "shell-derived-data"
        shutil.rmtree(shell_dir, ignore_errors=True); shutil.rmtree(shell_dd, ignore_errors=True); shell_dir.mkdir(parents=True)
        shell_env = os.environ.copy()
        shell_env.update({"SHELL_DIR": str(shell_dir), "DM_SHELL_FRAMEWORKS": str(framework),
            "DM_SHELL_PACKAGE": str(nx / "frontend-ios"), "DM_SHELL_NAME": display_name,
            "DM_BUNDLE_ID": "org.nxnative.spkioszero", "DM_APP_VERSION": display_version,
            "DM_TEAM_ID": "0000000000", "DM_XCODE_DERIVED_DATA": str(shell_dd),
            "FONT_PY": py, "STD_FONT": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"})
        print("[SpkIOSzero] Building the NX2Apple Shared Shell around the Sparking! ZERO framework...", flush=True)
        run(["bash", str(engine / "dm/ios/tools/build_shell.sh"), "--build"], cwd=engine, env=shell_env)
        app = shell_dd / "Build" / "Products" / "Release-iphoneos" / "DmShell.app"
        if not (app / "DmShell").is_file(): fail(f"Shared Shell app was not built: {app}")
        entitlements = shell_dir / "Gen" / "DmShell.entitlements"
        if not entitlements.is_file(): fail("build_shell.sh did not generate DmShell.entitlements.")
        embedded = sorted((app / "Frameworks").glob("*.framework"))
        if not any(item.name == framework_name for item in embedded): fail(f"Shared Shell did not embed {framework_name}.")
        for item in embedded:
            run(["xattr", "-cr", str(item)])
            run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(item)])
            run(["codesign", "--verify", "--strict", str(item)])
        run(["xattr", "-cr", str(app)])
        run(["codesign", "--force", "--sign", "-", "--entitlements", str(entitlements), "--timestamp=none", str(app)])
        run(["codesign", "--verify", "--deep", "--strict", str(app)])
        ent_check = subprocess.run(["codesign", "-d", "--entitlements", ":-", str(app / "DmShell")],
            capture_output=True, text=True, check=False)
        if "com.apple.developer.kernel.increased-memory-limit" not in (ent_check.stdout + ent_check.stderr):
            fail("Ad-hoc DmShell signature is missing Increased Memory Limit.")

        ipa = output / "SpkIOSzero.ipa"
        run([py, str(engine / "dm/ios/tools/pack_ipa.py"), str(ipa), "--no-reuse",
             f"Payload/DmShell.app={app}"], cwd=engine)
        with zipfile.ZipFile(ipa) as archive:
            entries = archive.namelist()
            required = ["Payload/DmShell.app/DmShell",
                f"Payload/DmShell.app/Frameworks/{framework_name}/{executable_name}",
                f"Payload/DmShell.app/Frameworks/{framework_name}/game.manifest.json"]
            missing = [name for name in required if name not in entries]
            if missing: fail("Final IPA is missing Route C components: " + ", ".join(missing))
            prohibited = [name for name in entries if name.lower().endswith("/romfs.img")
                or "/aoc/" in name.lower() or name.lower().endswith(".nsp")
                or name.lower().endswith("/prod.keys") or name.lower().endswith(".mtl4a")]
            if prohibited: fail("IPA unexpectedly embeds external game data, keys or unsupported PSO: " + ", ".join(prohibited[:20]))

        game_data = prepared["game_data"]
        report = {"project": PROJECT, "branch": BRANCH, "game": display_name, "title_id": TITLE_ID,
            "display_version": display_version, "package_version": prepared["package_version"],
            "nx2apple_tag": NX2APPLE_TAG, "engine_pin": ENGINE_PIN,
            "main_build_id": EXPECTED_MAIN_BUILD_ID, "main_sha256": EXPECTED_MAIN_SHA256,
            "allocator": prep["allocator"], "shader_chain": actual_chain, "shader_package_key": package_key,
            "framework": framework_name, "ipa": ipa.name, "ipa_size_bytes": ipa.stat().st_size,
            "build_architecture": {
                "colab_linux": ["Drive/spk base/update/DLC content-meta scan",
                    "NXNative base + update extraction and DLC AOC extraction",
                    "AArch64 rewrite with exact-build SPK allocator and SpNet cuts"],
                "macos": ["game-owned Unreal/Oodle shader decode", "NVN shader split including DLC AOC roots",
                    "iOS Metal shader compilation", "DM_FRAMEWORK_ONLY Route C framework",
                    "NX2Apple Shared Shell build", "ad-hoc signature and thin IPA packaging"],
                "mac_downloaded_original_nsp": False, "mac_downloaded_prod_keys": False,
                "mac_repeated_nsp_extraction": False},
            "ipa_contains_romfs": False, "ipa_contains_aoc": False, "ipa_contains_nsp": False, "ipa_contains_prod_keys": False,
            "external_game_data": {"drive_folder_url": game_data.get("folder_url"),
                "romfs_size_bytes": romfs.stat().st_size, "aoc_images": [p.name for p in aoc_images],
                "layout": f"games/{TITLE_ID}/romfs.img + games/{TITLE_ID}/aoc/"},
            "pipeline_archive": {"included": False, "gpu": "none",
                "reason": "No offline MTL4 PSO archive is embedded; the device builds PSO bases on first use."},
            "signature": "ad-hoc; sideloading re-sign is required",
            "entitlement": "com.apple.developer.kernel.increased-memory-limit"}
        (output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        print(f"[SpkIOSzero] IPA complete: {ipa} ({ipa.stat().st_size:,} bytes)", flush=True)
    finally:
        try: builder.PROG.close(ok=True)
        except Exception: pass

if __name__ == "__main__": main()
