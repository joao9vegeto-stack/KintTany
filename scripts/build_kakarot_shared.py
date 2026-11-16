#!/usr/bin/env python3
"""macOS ARM64 Route C: Kakarot Oodle/shader split -> iOS Metal -> DmGame.framework -> Shared Shell -> thin IPA."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

TITLE_ID = "010051C0134F8000"
PROJECT = "KaKaRoTiOS"
BRANCH = "KaKaRoTiOS"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"

def fail(message: str) -> None:
    raise SystemExit("[KaKaRoTiOS] ERROR: " + message)

def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)

def run(command, cwd=None, env=None) -> None:
    cmd = list(map(str, command))
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(str(value))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        fail(f"Unsafe {label} path: {value}")
    return path

def load_builder(engine: Path):
    for folder in (engine / "dm/tools", engine / "dm/games", engine / "dm/gfx/tools", engine / "scripts"):
        sys.path.insert(0, str(folder))
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    if not script.is_file():
        fail(f"Pinned NXNative builder is missing: {script}")
    for name in ("game", "nacp", "profile_guess", "nso", "nso_syms", "nso_asm",
                 "uepak", "uepak_extract", "nso_match", "sdk_patches", "romfs", "shader_lib"):
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location("kakarot_nxnative_builder", script)
    if spec is None or spec.loader is None:
        fail("Could not load pinned NXNative build_ipa_from_nsp.py.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    import game as game_profiles
    import nacp
    import profile_guess as pg
    module.gamemod = game_profiles
    module.nacp = nacp
    module.pg = pg
    return module, game_profiles, nacp, pg

def pak_audit(romfs_source) -> dict:
    """Recheck the Colab package-format/shader-source decision on macOS."""
    import uepak
    records = []
    for path in uepak.paks(str(romfs_source)):
        try:
            with uepak.open(path, "rb") as stream:
                encrypted, index_offset, index_size, methods, version = uepak.footer(stream)
            records.append({
                "path": str(Path(path).name),
                "version": int(version),
                "encrypted_index": bool(encrypted),
                "index_offset": int(index_offset),
                "index_size": int(index_size),
                "compression_methods": [str(x) for x in methods if str(x)],
                "inline_shaders": bool(uepak.inline_shaders(path)),
            })
        except (OSError, ValueError, struct.error) as exc:
            records.append({"path": str(Path(path).name), "unreadable": str(exc)})
    readable = [x for x in records if "version" in x]
    methods = {m.lower() for item in readable for m in item["compression_methods"]}
    return {
        "pak_count": len(records),
        "readable_pak_count": len(readable),
        "versions": sorted({x["version"] for x in readable}),
        "compression_methods": sorted(methods),
        "oodle_host_required": bool(methods & {"oodle", "lz5", "custom", "kraken", "mermaid"}),
        "records": records,
    }

def needs_oodle_host(actual_flags: dict, actual_paks: dict) -> bool:
    """UE legacy assets may require the game-owned Oodle/LZ5 decoder even when Pak v8 says Zlib."""
    return bool(
        actual_paks.get("oodle_host_required")
        or actual_flags.get("oodle_packs")
        or actual_flags.get("ue_legacy")
    )


def unreadable_shader_file_count(log_text: str) -> int:
    """Count cooked files omitted by NXNative shader split."""
    counts = re.findall(r"(\d+)\s+file\(s\)\s+could not be read\b", str(log_text), flags=re.IGNORECASE)
    return max((int(value) for value in counts), default=0)


def validate_shader_map(profile) -> Path:
    shader_map = Path(profile.table("shader_map.tsv"))
    if not shader_map.is_file() or shader_map.stat().st_size == 0:
        fail(f"Shader split did not produce a non-empty map: {shader_map}")
    return shader_map

def validate_table_stamp(profile, ios_msl: Path, chain: str) -> dict:
    import shader_lib
    library = ios_msl / f"b-{chain}"
    image = Path(str(library) + ".img")
    if not (library.is_dir() or image.is_file()):
        fail(f"Full iOS Metal library is missing: {library}(.img)")
    stamped_path = image if image.is_file() else library
    stamp = shader_lib.read_stamp(str(stamped_path))
    if stamp.get("game") != TITLE_ID:
        fail(f"iOS Metal library stamp names another game: {stamp.get('game')!r}.")
    inputs = stamp.get("inputs")
    if not inputs:
        fail("iOS Metal library has no profile-input digest stamp.")
    for name in ("c1_full.tsv", "cb_extent.tsv"):
        path = Path(profile.table(name))
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"Required full-build validation table is missing: {path}")
        first = path.read_text(encoding="utf-8", errors="replace").splitlines()[0] if path.stat().st_size else ""
        expected = f"# chain b-{chain} inputs {inputs} "
        if not first.startswith(expected):
            fail(f"{name} chain/input stamp mismatch. Expected prefix {expected!r}; found {first!r}.")
    inputs_tsv = (library / "inputs.tsv") if library.is_dir() else None
    if inputs_tsv is not None and inputs_tsv.is_file():
        rows = inputs_tsv.read_text(encoding="utf-8", errors="replace").splitlines()
        if f"game\t{TITLE_ID}" not in rows or f"inputs\t{inputs}" not in rows:
            fail("b-<chain>/inputs.tsv does not match the Kakarot profile and table digest.")
    return {"library": str(stamped_path), "chain": chain, "game": stamp["game"],
            "inputs": inputs, "c1_full": str(profile.table("c1_full.tsv")),
            "cb_extent": str(profile.table("cb_extent.tsv"))}

def validate_workspace(prepared: dict, work: Path, nx: Path, builder, game_profiles):
    if prepared.get("project") != PROJECT or prepared.get("branch") != BRANCH:
        fail("Prepared input does not belong to the KaKaRoTiOS project/branch.")
    if prepared.get("title_id") != TITLE_ID or not prepared.get("package_version"):
        fail("Prepared input Title ID/package version is invalid.")
    if prepared.get("nx2apple_tag") != NX2APPLE_TAG or prepared.get("engine_pin") != ENGINE_PIN:
        fail("NX2Apple/NXNative pin mismatch.")
    pin_file = nx / ".upstream-ref"
    if not pin_file.is_file() or pin_file.read_text(encoding="utf-8").strip() != ENGINE_PIN:
        fail("Checked-out NXNative engine does not match the pinned commit.")

    prep_path = work / "kakarot-linux-prep.json"
    if not prep_path.is_file():
        fail("Colab Linux preparation manifest is missing.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    for key in ("project", "title_id", "package_version", "nx2apple_tag", "engine_pin",
                "profile_type", "profile_source", "profile_relative_dir",
                "modules", "main_build_id", "main_sha256", "rewrite_audit",
                "graphics_api", "unreal_shader_sources", "pak_audit", "shader_chain",
                "romfs_relative_path", "romfs_id_relative_path",
                "romfs_size", "romfs_sha256", "aoc_relative_dir", "aoc_count",
                "survey_relative_path", "survey_size", "survey_sha256",
                "input_package_count", "input_dlc_package_count", "input_packages"):
        if prepared.get(key) != prep.get(key):
            fail(f"Actions input and Colab workspace disagree on {key}.")
    if prepared.get("aoc_image_manifest") != prep.get("aoc_images"):
        fail("Actions AOC metadata manifest differs from the Colab preparation manifest.")
    if prep.get("profile_type") != "provisional":
        fail("Route C expects the Kakarot profile generated from the actual NSP/XCI content.")
    input_packages = prep.get("input_packages", [])
    input_dlcs = [item for item in input_packages if str(item.get("name", "")).startswith("dlc_")]
    if (prep.get("input_package_count") != 22 or len(input_packages) != 22
            or prep.get("input_dlc_package_count") != 20 or len(input_dlcs) != 20):
        fail("Route C expects exactly base + update + 20 DLC inputs (22 NXNative packages).")
    if prep.get("graphics_api") != "nvn":
        fail(f"Kakarot graphics API is not NVN: {prep.get('graphics_api')}.")
    if builder.chain_of(nx / "engine") != prepared.get("shader_chain"):
        fail("Shader-chain drift: Colab and the pinned macOS engine do not agree.")
    if prepared.get("aoc_count") != prep.get("aoc_count"):
        fail("Actions and Colab AOC counts disagree.")

    profile_rel = safe_relative(prep["profile_relative_dir"], "profile")
    profile_dir = work.joinpath(*profile_rel.parts)
    profile_file = profile_dir / "game.tsv"
    if not profile_file.is_file():
        fail(f"Generated game.tsv is missing: {profile_file}")
    profile_text = profile_file.read_text(encoding="utf-8")
    if "Provisional game profile" not in profile_text:
        fail("Restored game.tsv is not the NXNative-generated provisional Kakarot profile.")
    os.environ["DM_GAMES_DIR"] = str(profile_dir.parent)
    os.environ["DM_GAMES_FIRST"] = "1"
    os.environ["DM_GAME"] = TITLE_ID
    profile = game_profiles.load(TITLE_ID)
    if profile.dir.resolve() != profile_dir.resolve():
        fail(f"NXNative loaded a profile other than the restored Kakarot profile: {profile.dir}")

    version_dir = work / "extract" / prep["package_version"]
    exefs = version_dir / "ExeFS"
    romfs_rel = safe_relative(prep["romfs_relative_path"], "RomFS")
    identity_rel = safe_relative(prep["romfs_id_relative_path"], "RomFS identity")
    romfs = work.joinpath(*romfs_rel.parts)
    identity = work.joinpath(*identity_rel.parts)
    survey_rel = safe_relative(prep["survey_relative_path"], "survey")
    survey = work.joinpath(*survey_rel.parts)
    if not survey.is_file() or survey.stat().st_size != int(prep["survey_size"]):
        fail("Restored NXNative Kakarot survey report is missing or has the wrong size.")
    if sha256_file(survey) != prep["survey_sha256"]:
        fail("Restored NXNative Kakarot survey SHA-256 differs from Colab.")
    if prepared.get("survey_path") != str(survey):
        fail("Actions input survey path does not point to the restored Kakarot survey.")
    aoc_rel = safe_relative(prep.get("aoc_relative_dir", "aoc"), "AOC")
    aoc_dir = work.joinpath(*aoc_rel.parts)
    if prepared.get("aoc_dir") != str(aoc_dir):
        fail("Actions input AOC path does not point to the restored Drive AOC directory.")
    aoc_dir.mkdir(parents=True, exist_ok=True)
    aoc_images = sorted(p for p in aoc_dir.glob("*.img") if p.is_file() and not p.is_symlink())
    if {p.name for p in aoc_images} != {x["name"] for x in prep.get("aoc_images", [])}:
        fail("Restored AOC image names differ from the Colab preparation manifest.")
    for path in aoc_images:
        item = next(x for x in prep["aoc_images"] if x["name"] == path.name)
        if path.stat().st_size != int(item["size"]) or sha256_file(path) != item["sha256"]:
            fail(f"Restored AOC image size/SHA-256 mismatch: {path.name}")
    if len(aoc_images) != int(prep.get("aoc_count", -1)):
        fail("Restored AOC image count differs from the preparation manifest.")
    if prepared.get("aoc_images") != [str(p) for p in aoc_images]:
        fail("Actions AOC image path list differs from the restored AOC data.")

    patched = work / f"patched_{prep['package_version']}"
    for path, label in (
        (exefs / "main", "extracted main"),
        (exefs / "main.npdm", "main.npdm"),
        (patched / "main.patched.bin", "ARM64 rewritten main"),
        (patched / "main.fixups.tsv", "main fixups"),
        (patched / "main.cuts.tsv", "main cuts audit"),
        (patched / "main.obs.tsv", "main observation audit"),
        (romfs, "external RomFS"),
        (identity, "RomFS identity sidecar"),
    ):
        if not path.is_file():
            fail(f"{label} is missing: {path}")
    if builder.build_id(exefs / "main") != prep["main_build_id"]:
        fail("Extracted main Build ID differs from Colab.")
    if sha256_file(exefs / "main") != prep["main_sha256"]:
        fail("Extracted main SHA-256 differs from Colab.")
    if int(romfs.stat().st_size) != int(prep["romfs_size"]):
        fail("Restored RomFS size differs from Colab.")
    if sha256_file(romfs) != prep["romfs_sha256"]:
        fail("Restored RomFS SHA-256 differs from Colab.")
    try:
        identity_json = json.loads(identity.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"Invalid RomFS identity sidecar: {exc}")
    if (identity_json.get("title") != TITLE_ID.lower()
            or identity_json.get("version") != prep["package_version"]
            or identity_json.get("bytes") != prep["romfs_size"]
            or identity_json.get("sha256") != prep["romfs_sha256"]):
        fail("RomFS identity sidecar does not match title/version/size/SHA-256.")

    modules = profile.modules_in(exefs)
    if sorted(modules) != sorted(prep["modules"]):
        fail(f"Loaded profile modules differ from Colab: {modules} != {prep['modules']}.")
    for name in modules:
        if not (patched / f"{name}.patched.bin").is_file():
            fail(f"Rewritten module is missing: {name}")
        if not (patched / f"{name}.fixups.tsv").is_file():
            fail(f"Rewrite fixups are missing: {name}")
    for item in (prep.get("rewrite_audit") or {}).get("module_artifacts", []):
        name = item["name"]
        if sha256_file(patched / f"{name}.patched.bin") != item["patched_sha256"]:
            fail(f"Rewritten ARM64 module SHA-256 mismatch: {name}.patched.bin")
        if sha256_file(patched / f"{name}.fixups.tsv") != item["fixups_sha256"]:
            fail(f"Rewrite fixup audit SHA-256 mismatch: {name}.fixups.tsv")
    return profile, version_dir, romfs, identity, patched, prep, modules, aoc_dir, aoc_images

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--prepared-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        fail("KaKaRoTiOS Route C must run on macOS ARM64.")
    if not os.uname().machine.startswith("arm"):
        fail(f"Route C requires an Apple Silicon ARM64 runner; got {os.uname().machine}.")
    nx = args.nx2apple_root.resolve()
    prepared = json.loads(args.prepared_json.read_text(encoding="utf-8"))
    work = Path(prepared["work_dir"]).resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    engine = nx / "engine"
    repo_scripts = Path(__file__).resolve().parent
    sys.path.insert(0, str(repo_scripts))
    builder, game_profiles, nacp, pg = load_builder(engine)
    # The provisional profile must be first in all engine-side lookups.
    profile_parent = work / "profile"
    os.environ.update({"DM_GAMES_DIR": str(profile_parent), "DM_GAMES_FIRST": "1", "DM_GAME": TITLE_ID})
    profile, version_dir, romfs, romfs_id, patched, prep, modules, aoc_dir, aoc_images = validate_workspace(
        prepared, work, nx, builder, game_profiles)

    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(parents=True, exist_ok=True)
    (work / "ipa").mkdir(parents=True, exist_ok=True)
    py = sys.executable
    env = builder.tool_env()
    env.setdefault("USER", os.environ.get("USER") or "runner")
    runner_cpus = os.cpu_count() or 0
    if runner_cpus < 3:
        fail(f"NXNative shader compilation requires at least 3 Apple Silicon CPUs; this runner exposes {runner_cpus}.")
    shader_threads = 8
    dmsh_procs = shader_threads
    memory_bytes = int(subprocess.run(
        ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True
    ).stdout.strip())
    if memory_bytes < 6 * 1024**3:
        fail(
            f"NXNative shader compilation requires at least 6 GiB RAM; this runner exposes "
            f"{memory_bytes / 1024**3:.1f} GiB."
        )
    env.update({"DM_GAME": TITLE_ID, "DM_GAMES_DIR": str(profile_parent),
                "DM_GAMES_FIRST": "1", "DM_ROOT": str(work),
                "WORK": str(work / "tmp"), "IOS_PULL": "1",
                "J": str(shader_threads), "DMSH_PROCS": str(dmsh_procs)})
    print(
        f"[KaKaRoTiOS] NXNative GIL-free Metal finish workers; J={env['J']}, "
        f"DMSH_PROCS={env['DMSH_PROCS']}, batch={4 * shader_threads}; "
        f"runner={runner_cpus} CPUs/{memory_bytes / 1024**3:.1f} GiB RAM.",
        flush=True,
    )
    builder.configure_dotnet(env)
    xlate = engine / "dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate"
    builder.PROG.mode = "lines"
    builder.PROG.plan(6)
    try:
        print("[KaKaRoTiOS] Checking the pinned Xcode/iOS SDK, translator and Metal toolchain...", flush=True)
        builder.check_prereqs(env, xlate, mac=False)
        builder.check_metal(py, engine, env)
        builder.chain_header(py, engine, env, logs)
        actual_chain = builder.chain_of(engine)
        if actual_chain != prepared["shader_chain"]:
            fail(f"Shader chain differs from Colab: {actual_chain} != {prepared['shader_chain']}.")

        # Complete the NXNative provisional-profile path on macOS ARM64. Colab cannot
        # execute the Apple host; this is where heap size and VA-region use are measured.
        builder.provisional_prep(py, engine, env, logs, profile)
        profile = builder.refine_after_rewrite(profile, version_dir, patched)
        if (builder.HEAP_CHECK and not builder.heap_checked(profile)
                and pg.heap_check_needed(version_dir / "ExeFS")):
            if not builder.apple_silicon():
                fail("Kakarot's provisional heap check requires the macOS ARM64 host.")
            print("[KaKaRoTiOS] Measuring the provisional heap and guest memory split on the Mac host...", flush=True)
            builder.PROG.add(1)
            profile = builder.heap_check(engine, version_dir, patched, work, env, logs, profile)
        if (builder.HEAP_CHECK and pg.has_va(version_dir / "ExeFS")
                and not builder.region_checked(profile, patched)):
            if not builder.apple_silicon():
                fail("Kakarot's virtual-address region check requires the macOS ARM64 host.")
            print("[KaKaRoTiOS] Measuring guest virtual-address region usage against the iPhone alias budget...", flush=True)
            builder.PROG.add(1)
            profile = builder.region_check(engine, version_dir, patched, work, env, logs, profile)
        profile = game_profiles.load(TITLE_ID)
        if profile.dir.resolve() != (work / "profile" / TITLE_ID).resolve():
            fail("The Mac bring-up selected a profile other than the Kakarot workspace profile.")

        romfs_source = builder.rfs.source(version_dir)
        facts = pg.build_sources(version_dir / "ExeFS", romfs_source, modules)
        if facts["graphics"][0] != prep["graphics_api"]:
            fail(f"Graphics API differs from Colab: {facts['graphics'][0]} != {prep['graphics_api']}.")
        actual_flags = {key: bool(facts.get(key, (False, ""))[0])
                        for key in ("ue_decode", "oodle_packs", "ue_legacy",
                                    "glslc_capture", "vk_capture", "gl_capture")}
        if actual_flags != prep["unreal_shader_sources"]:
            fail(f"Shader source classification differs between Colab and macOS: {actual_flags} != {prep['unreal_shader_sources']}.")
        actual_paks = pak_audit(romfs_source)
        if actual_paks != prep["pak_audit"]:
            fail("Unreal PAK versions/compression/index audit differs between Colab and macOS.")
        if actual_paks["readable_pak_count"] == 0:
            fail("No readable Kakarot Unreal PAKs are present on macOS.")

        if actual_flags["ue_decode"]:
            print("[KaKaRoTiOS] Running NXNative's Unreal shader archive extraction and game-owned Oodle decoder on macOS ARM64...", flush=True)
            builder.decode_ue_shaders(engine, {prepared["package_version"]: version_dir},
                prepared["package_version"], patched, work, env, logs, profile)
            decoded_dir = version_dir / "ue_shaders"
            decoded = sorted(decoded_dir.glob("*.ushaderbytecode")) if decoded_dir.is_dir() else []
            if not decoded:
                fail("Unreal/Oodle decode stage did not produce .ushaderbytecode archives.")
        else:
            print("[KaKaRoTiOS] This build has no separate Oodle shader-code archive; shader data is inline in Unreal cooked packages.", flush=True)

        # Match Mugiwara4iOS: UE legacy is itself a reason to expose the game-owned
        # Oodle/LZ5 decoder. Pak v8 can report Zlib for its index while individual
        # legacy cooked assets still use Oodle/LZ5, so the PAK method list alone
        # is not a sufficient detector for Kakarot.
        need_oodle_host = needs_oodle_host(actual_flags, actual_paks)
        oodle = None
        if need_oodle_host:
            print(
                "[KaKaRoTiOS] Oodle/LZ5 decoder required ("
                f"oodle_packs={actual_flags['oodle_packs']}, "
                f"ue_legacy={actual_flags['ue_legacy']}, "
                f"pak_audit={actual_paks['oodle_host_required']}); "
                "building the macOS ARM64 helper host...",
                flush=True,
            )
            oodle = lambda: {
                "DM_OODLE_HOST": str(builder.build_mac_host(engine, work / "tools" / "dmhost", env, logs, profile)),
                "DM_OODLE_MODULES": str(patched),
            }
        else:
            print("[KaKaRoTiOS] PAK audit and profile classification confirm no game-owned Oodle/LZ5 decoder is required.", flush=True)

        print("[KaKaRoTiOS] Splitting Kakarot shaders on macOS using the exact rewritten main, RomFS and generated profile...", flush=True)
        shader_package = work / "shader" / "pkg"
        package_key = builder.split_shaders(
            py, engine, [romfs_source], [version_dir / "ExeFS" / "main"],
            shader_package, env, logs, profile, provisional=True, oodle=oodle, dlc_roms=aoc_images)
        split_log = logs / "shader_split.log"
        if not split_log.is_file():
            fail(f"Shader split log is missing; cannot verify cooked-file readability: {split_log}")
        unreadable_files = unreadable_shader_file_count(
            split_log.read_text(encoding="utf-8", errors="replace")
        )
        if unreadable_files:
            fail(
                f"Shader split left {unreadable_files} cooked file(s) unreadable; "
                "refusing to compile an incomplete Metal library/IPA. "
                f"Inspect {split_log}."
            )
        print("[KaKaRoTiOS] Shader split readability gate: 0 cooked files omitted.", flush=True)
        if not isinstance(package_key, str) or not re.fullmatch(r"[0-9a-f]{64}", package_key):
            fail("NXNative shader split did not return a valid SHA-256 package key.")
        if builder.package_key(shader_package) != package_key:
            fail("Shader package content key does not match the split result.")
        shader_map = validate_shader_map(profile)
        print(f"[KaKaRoTiOS] Shader map generated: {shader_map} ({shader_map.stat().st_size:,} bytes).", flush=True)

        gpu_selection = builder.ios_gpus("none", profile)
        pull = builder.ios_wants_pulling(profile, gpu_selection, False, env)
        print(f"[KaKaRoTiOS] Compiling iOS Metal libraries; pulling libraries: {'yes' if pull else 'no'}...", flush=True)
        ios_msl = builder.build_shaders(
            py, engine, work / "shader", xlate, env, logs, profile,
            pkg_key=package_key, mac=False, seen=None, pull=pull)
        chain_lib = ios_msl / f"b-{actual_chain}"
        chain_img = Path(str(chain_lib) + ".img")
        if not (chain_lib.is_dir() or chain_img.is_file()):
            fail(f"iOS Metal shader library is missing: {chain_lib}(.img).")
        table_stamp = validate_table_stamp(profile, ios_msl, actual_chain)
        print("[KaKaRoTiOS] c1_full.tsv, cb_extent.tsv and Metal chain input stamp all verified.", flush=True)

        control = builder.languages_control(version_dir)
        display_name = nacp.name(control) or profile.get("name") or "DRAGON BALL Z: KAKAROT"
        display_version = nacp.version(version_dir / "control.nacp") or "1.0.0"
        language = builder.game_language("en-US", False, nacp.languages(control))
        framework_root = output / "frameworks"
        shutil.rmtree(framework_root, ignore_errors=True)
        framework_root.mkdir(parents=True)
        ipa_env = dict(env)
        ipa_env.update({
            "GAME": TITLE_ID, "W": str(work / "ipa"), "PATCHED": str(patched),
            "ROMFS": str(romfs), "MSL_IOS": str(ios_msl), "GFXAPI": "nvn",
            "FONT_PY": py, "DM_DISPLAY_NAME": display_name, "DM_APP_VERSION": display_version,
            "DM_BUNDLE_ID": f"org.nxnative.{TITLE_ID.lower()}",
            "DM_XCODE_DERIVED_DATA": str(work / "xcode-derived-data"),
            "DM_TEAM_ID": "0000000000", "DM_LANG": language, "CONTROL": str(control),
            "AOC": "", "DM_COPY_ROMFS": "NO", "DM_PSO_GPUS": "none",
            "DM_SHOW_FPS": "1", "DM_FRAMEWORK_ONLY": str(framework_root), "IOS_PULL": "1",
        })
        print("[KaKaRoTiOS] Building DmGame.framework through NXNative DM_FRAMEWORK_ONLY; RomFS stays external.", flush=True)
        run(["bash", str(engine / "dm/ios/tools/build_ipa.sh")], cwd=engine, env=ipa_env)

        framework_name = f"DmGame{TITLE_ID}.framework"
        framework = framework_root / framework_name
        manifest_path = framework / "game.manifest.json"
        if not manifest_path.is_file():
            fail(f"NXNative framework manifest is missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        executable_name = manifest.get("framework_executable", "")
        if str(manifest.get("title_id", "")).upper() != TITLE_ID:
            fail("Framework manifest Title ID does not match Kakarot.")
        if manifest.get("framework") != framework_name or executable_name != framework_name.removesuffix(".framework"):
            fail("Framework name/executable does not match the Kakarot Title ID.")
        if manifest.get("chain") != f"b-{actual_chain}":
            fail("Framework manifest shader chain differs from the compiled Metal chain.")
        for rel in (executable_name, "profile.tsv", "dm/shader_map.tsv", "dm/c1_full.tsv", "dm/cb_extent.tsv"):
            if not (framework / rel).is_file():
                fail(f"Framework is missing required Route C component {rel}.")
        if not (framework / "msl" / f"b-{actual_chain}.img").is_file():
            if not (framework / "msl" / f"b-{actual_chain}").is_dir():
                fail("Framework does not contain the iOS Metal library for the verified chain.")
        if any(framework.rglob("*.mtl4a")):
            fail("Framework unexpectedly contains an unsupported .mtl4a PSO archive.")
        if (framework / "pso").exists() and any((framework / "pso").iterdir()):
            fail("DM_PSO_GPUS=none should not embed an offline PSO archive.")

        shell_dir = output / "shell-project"
        shell_dd = output / "shell-derived-data"
        shutil.rmtree(shell_dir, ignore_errors=True)
        shutil.rmtree(shell_dd, ignore_errors=True)
        shell_dir.mkdir(parents=True)
        shell_env = os.environ.copy()
        shell_env.update({
            "SHELL_DIR": str(shell_dir), "DM_SHELL_FRAMEWORKS": str(framework),
            "DM_SHELL_PACKAGE": str(nx / "frontend-ios"), "DM_SHELL_NAME": display_name,
            "DM_BUNDLE_ID": "org.nxnative.kakarotios",
            "DM_APP_VERSION": display_version, "DM_TEAM_ID": "0000000000",
            "DM_XCODE_DERIVED_DATA": str(shell_dd), "FONT_PY": py,
            "STD_FONT": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        })
        print("[KaKaRoTiOS] Building the NX2Apple Shared Shell around DmGame.framework...", flush=True)
        run(["bash", str(engine / "dm/ios/tools/build_shell.sh"), "--build"], cwd=engine, env=shell_env)
        app = shell_dd / "Build" / "Products" / "Release-iphoneos" / "DmShell.app"
        if not (app / "DmShell").is_file():
            fail(f"Shared Shell app was not built: {app}")
        entitlements = shell_dir / "Gen" / "DmShell.entitlements"
        if not entitlements.is_file():
            fail("build_shell.sh did not generate DmShell.entitlements.")
        embedded = sorted((app / "Frameworks").glob("*.framework"))
        if not any(item.name == framework_name for item in embedded):
            fail(f"Shared Shell did not embed {framework_name}.")
        for item in embedded:
            run(["xattr", "-cr", str(item)])
            run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(item)])
            run(["codesign", "--verify", "--strict", str(item)])
        run(["xattr", "-cr", str(app)])
        run(["codesign", "--force", "--sign", "-", "--entitlements", str(entitlements),
             "--timestamp=none", str(app)])
        run(["codesign", "--verify", "--deep", "--strict", str(app)])
        ent_check = subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", str(app / "DmShell")],
            capture_output=True, text=True, check=False)
        if "com.apple.developer.kernel.increased-memory-limit" not in (ent_check.stdout + ent_check.stderr):
            fail("Ad-hoc Shared Shell signature is missing Increased Memory Limit.")

        ipa = output / "KaKaRoTiOS.ipa"
        run([py, str(engine / "dm/ios/tools/pack_ipa.py"), str(ipa), "--no-reuse",
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
                fail("Final IPA is missing Route C components: " + ", ".join(missing))
            prohibited = [name for name in entries if
                name.lower().endswith("/romfs.img")
                or name.lower().endswith(".nsp") or name.lower().endswith(".xci")
                or name.lower().endswith("/prod.keys")
                or "/aoc/" in name.lower()
                or name.lower().endswith(".mtl4a")]
            if prohibited:
                fail("Thin IPA unexpectedly embeds external game data, original packages, keys or unsupported PSO: "
                     + ", ".join(prohibited[:20]))

        report = {
            "project": PROJECT, "branch": BRANCH, "game": display_name,
            "title_id": TITLE_ID, "display_version": display_version,
            "package_version": prepared["package_version"],
            "nx2apple_tag": NX2APPLE_TAG, "engine_pin": ENGINE_PIN,
            "profile_type": prep["profile_type"], "profile_source": prep["profile_source"],
            "main_build_id": prep["main_build_id"], "main_sha256": prep["main_sha256"],
            "modules": modules, "rewrite_audit": prep["rewrite_audit"],
            "graphics_api": prep["graphics_api"],
            "unreal_shader_sources": actual_flags, "pak_audit": actual_paks,
            "shader_chain": actual_chain, "shader_package_key": package_key,
            "metal_validation": table_stamp,
            "framework": framework_name, "ipa": ipa.name, "ipa_size_bytes": ipa.stat().st_size,
            "pipeline": [
                "Colab three-volume BASE RAR verification/CRC extraction + direct UPDATE NSP transfer and package-header/SHA-256 validation",
                "Drive base/update package checkpoints and RAR cleanup after MD5/SHA-256 verification",
                "NXNative metadata scan and Kakarot provisional profile",
                "NXNative ARM64 rewrite and fixup audit",
                "Drive workspace/RomFS/AOC split with SHA-256 validation",
                "GitHub Actions macOS ARM64 conditional Oodle processing",
                "Unreal shader split and profile shader table generation",
                "iOS Metal compile, c1_full/cb_extent and chain/input stamp validation",
                "DmGame.framework build", "NX2Apple Shared Shell build",
                "ad-hoc signature and thin IPA packaging",
            ],
            "external_game_data": {
                "drive_folder_url": (prepared.get("game_data") or {}).get("folder_url"),
                "base_package": prepared.get("base_package"),
                "update_package": prepared.get("update_package"),
                "romfs_size_bytes": romfs.stat().st_size,
                "romfs_sha256": sha256_file(romfs),
                "aoc_folder_url": (prepared.get("game_data") or {}).get("aoc_folder_url"),
                "aoc_count": len(aoc_images),
                "aoc_images": [{"name": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)} for p in aoc_images],
                "layout": f"games/{TITLE_ID.lower()}/base.<nsp|xci> + update.<nsp|xci> + romfs.img + aoc/",
            },
            "ipa_contains_base_package": False, "ipa_contains_update_package": False,
            "ipa_contains_romfs": False, "ipa_contains_aoc": False,
            "ipa_contains_nsp": False, "ipa_contains_xci": False,
            "ipa_contains_prod_keys": False,
            "pipeline_archive": {"included": False, "gpu": "none",
                "reason": "No offline MTL4 PSO archive is embedded; device-side pipeline creation remains available."},
            "signature": "ad-hoc; sideloading re-sign may be required",
            "entitlement": "com.apple.developer.kernel.increased-memory-limit",
            "runtime_validation": "Not performed by this build job; install and test on the target iPhone after IPA delivery.",
        }
        (output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        print(f"[KaKaRoTiOS] IPA complete: {ipa} ({ipa.stat().st_size:,} bytes).", flush=True)
    finally:
        try:
            builder.PROG.close(ok=True)
        except Exception:
            pass

if __name__ == "__main__":
    main()
