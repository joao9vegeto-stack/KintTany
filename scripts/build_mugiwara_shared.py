#!/usr/bin/env python3
"""macOS ARM64 Route C: One Piece: Pirate Warriors 4 Oodle/shader split -> iOS Metal -> DmGame.framework -> Shared Shell -> thin IPA."""
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

TITLE_ID = "01008FE00E2F6000"
PROJECT = "Mugiwara4iOS"
BRANCH = "Mugiwara4iOS"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"

def fail(message: str) -> None:
    raise SystemExit("[Mugiwara4iOS] ERROR: " + message)

def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)

def valid_aoc_manifest(prep: dict) -> bool:
    """Validate one external AOC per unique DLC Title ID, matching NXNative's selection."""
    try:
        count = prep.get("aoc_count")
        title_ids = prep.get("aoc_title_ids")
        contents = prep.get("aoc_contents")
        images = prep.get("aoc_images")
        dlc_meta = prep.get("dlc_content_meta")
        packages = prep.get("input_packages")
        if type(count) is not int or not 1 <= count <= 44:
            return False
        if not all(isinstance(x, list) for x in (title_ids, contents, images, dlc_meta, packages)):
            return False
        if (len(title_ids) != count or len(set(title_ids)) != count
                or len(contents) != count or len(images) != count
                or len(dlc_meta) < 44 or prep.get("dlc_content_meta_count") != len(dlc_meta)):
            return False
        app = int(TITLE_ID, 16)
        dlc_packages = {
            item.get("local_name"): item for item in packages
            if item.get("role") == "dlc" and item.get("type") == "NSP"
        }
        if len(dlc_packages) != 44:
            return False
        best = {}
        for item in dlc_meta:
            tid_text = item.get("title_id", "")
            if (not isinstance(tid_text, str) or len(tid_text) != 16
                    or f"{int(tid_text, 16):016X}" != tid_text
                    or item.get("source_package") not in dlc_packages):
                return False
            tid = int(tid_text, 16)
            version = int(item.get("content_version", -1))
            package = dlc_packages[item["source_package"]]
            key = (version, int(package.get("size", 0)))
            if version < 0 or key[1] <= 0:
                return False
            if tid not in best or key > best[tid][0]:
                best[tid] = (key, item["source_package"], version)
        if set(title_ids) != {f"{tid:016X}" for tid in best}:
            return False
        if {item.get("source_package") for item in dlc_meta} != set(dlc_packages):
            return False
        content_by_title = {item.get("title_id"): item for item in contents}
        if len(content_by_title) != count or set(content_by_title) != set(title_ids):
            return False
        expected_names = set()
        for tid in sorted(best):
            title = f"{tid:016X}"
            index = tid - app - 0x1000
            name = f"{index}.img"
            expected_names.add(name)
            item = content_by_title[title]
            selected_package = dlc_packages[best[tid][1]]
            if (index <= 0 or item.get("aoc_index") != index or item.get("name") != name
                    or item.get("content_version") != best[tid][2]
                    or item.get("source_package") != best[tid][1]
                    or item.get("source_size") != int(selected_package.get("size", 0))
                    or item.get("source_sha256") != selected_package.get("sha256")):
                return False
        image_by_name = {item.get("name"): item for item in images}
        if len(image_by_name) != count or set(image_by_name) != expected_names:
            return False
        for title, content in content_by_title.items():
            image = image_by_name[content["name"]]
            digest = image.get("sha256", "")
            if (image.get("title_id") != title or image.get("aoc_index") != content["aoc_index"]
                    or int(image.get("size", 0)) <= 0 or len(digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in digest.lower())):
                return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


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
    spec = importlib.util.spec_from_file_location("mugiwara_nxnative_builder", script)
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
            fail("b-<chain>/inputs.tsv does not match the One Piece: Pirate Warriors 4 profile and table digest.")
    return {"library": str(stamped_path), "chain": chain, "game": stamp["game"],
            "inputs": inputs, "c1_full": str(profile.table("c1_full.tsv")),
            "cb_extent": str(profile.table("cb_extent.tsv"))}

def validate_workspace(prepared: dict, work: Path, nx: Path, builder, game_profiles):
    if prepared.get("project") != PROJECT or prepared.get("branch") != BRANCH:
        fail("Prepared input does not belong to the Mugiwara4iOS project/branch.")
    if prepared.get("title_id") != TITLE_ID or not prepared.get("package_version"):
        fail("Prepared input Title ID/package version is invalid.")
    if prepared.get("nx2apple_tag") != NX2APPLE_TAG or prepared.get("engine_pin") != ENGINE_PIN:
        fail("NX2Apple/NXNative pin mismatch.")
    pin_file = nx / ".upstream-ref"
    if not pin_file.is_file() or pin_file.read_text(encoding="utf-8").strip() != ENGINE_PIN:
        fail("Checked-out NXNative engine does not match the pinned commit.")

    prep_path = work / "mugiwara4ios-linux-prep.json"
    if not prep_path.is_file():
        fail("Colab Linux preparation manifest is missing.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    if prep.get("format") != 4 or not isinstance(prep.get("jit_required"), bool):
        fail("Colab prep manifest is outdated or missing the unique-title-ID AOC and NXNative nn::jit/AOT contract; rerun Colab preparation.")
    for key in ("format", "project", "title_id", "package_version", "display_version",
                "base_content_version", "update_content_version", "nx2apple_tag", "engine_pin",
                "profile_type", "profile_source", "profile_relative_dir",
                "modules", "main_build_id", "main_sha256", "rewrite_audit",
                "graphics_api", "jit_required", "shader_source_flags", "shader_source_reasons", "shader_source_audit", "shader_chain",
                "romfs_relative_path", "romfs_id_relative_path", "romfs_size", "romfs_sha256",
                "aoc_relative_dir", "aoc_count", "aoc_title_ids", "aoc_contents", "aoc_images",
                "dlc_content_meta_count", "dlc_content_meta", "survey_relative_path", "survey_size",
                "survey_sha256", "input_package_count", "input_nsp_count", "input_xci_count",
                "input_update_nsp_count", "input_dlc_nsp_count", "input_packages"):
        if prepared.get(key) != prep.get(key):
            fail(f"Actions input and Colab workspace disagree on {key}.")
    if (prep.get("display_version") != "1.8.7" or prep.get("base_content_version") != 0
            or int(prep.get("update_content_version", 0)) <= 0):
        fail("Route C expects base content v0 and the update NACP display version 1.8.7.")
    if prep.get("profile_type") != "provisional":
        fail("Route C expects the One Piece: Pirate Warriors 4 profile generated from the actual NSP/XCI content.")
    if (prep.get("input_package_count") != 46 or prep.get("input_nsp_count") != 46
            or prep.get("input_xci_count") != 0 or prep.get("input_update_nsp_count") != 1
            or prep.get("input_dlc_nsp_count") != 44 or len(prep.get("input_packages", [])) != 46):
        fail("Route C expects exactly 1 base NSP + 1 update NSP + 44 DLC NSPs.")
    if not valid_aoc_manifest(prep):
        fail("Route C AOC manifest does not match the 44 source DLC NSPs and NXNative's unique-title-ID/highest-version selection.")
    if prep.get("graphics_api") != "nvn":
        fail(f"One Piece: Pirate Warriors 4 graphics API is not NVN: {prep.get('graphics_api')}.")
    if builder.chain_of(nx / "engine") != prepared.get("shader_chain"):
        fail("Shader-chain drift: Colab and the pinned macOS engine do not agree.")

    profile_rel = safe_relative(prep["profile_relative_dir"], "profile")
    profile_dir = work.joinpath(*profile_rel.parts)
    profile_file = profile_dir / "game.tsv"
    if not profile_file.is_file():
        fail(f"Generated game.tsv is missing: {profile_file}")
    profile_text = profile_file.read_text(encoding="utf-8")
    if "Provisional game profile" not in profile_text:
        fail("Restored game.tsv is not the NXNative-generated provisional One Piece: Pirate Warriors 4 profile.")
    os.environ["DM_GAMES_DIR"] = str(profile_dir.parent)
    os.environ["DM_GAMES_FIRST"] = "1"
    os.environ["DM_GAME"] = TITLE_ID
    profile = game_profiles.load(TITLE_ID)
    if profile.dir.resolve() != profile_dir.resolve():
        fail(f"NXNative loaded a profile other than the restored One Piece: Pirate Warriors 4 profile: {profile.dir}")

    version_dir = work / "extract" / prep["package_version"]
    exefs = version_dir / "ExeFS"
    actual_jit = bool(builder.uses_jit(exefs))
    if actual_jit != prep["jit_required"]:
        fail(f"nn::jit import scan differs between Colab and macOS: {actual_jit} != {prep['jit_required']}.")
    romfs_rel = safe_relative(prep["romfs_relative_path"], "RomFS")
    identity_rel = safe_relative(prep["romfs_id_relative_path"], "RomFS identity")
    romfs = work.joinpath(*romfs_rel.parts)
    identity = work.joinpath(*identity_rel.parts)
    aoc_rel = safe_relative(prep["aoc_relative_dir"], "AOC")
    aoc_dir = work.joinpath(*aoc_rel.parts)
    survey_rel = safe_relative(prep["survey_relative_path"], "survey")
    survey = work.joinpath(*survey_rel.parts)
    if not survey.is_file() or survey.stat().st_size != int(prep["survey_size"]):
        fail("Restored NXNative One Piece: Pirate Warriors 4 survey report is missing or has the wrong size.")
    if sha256_file(survey) != prep["survey_sha256"]:
        fail("Restored NXNative One Piece: Pirate Warriors 4 survey SHA-256 differs from Colab.")
    if prepared.get("survey_path") != str(survey):
        fail("Actions input survey path does not point to the restored One Piece: Pirate Warriors 4 survey.")
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
    if not aoc_dir.is_dir():
        fail(f"External DLC AOC directory is missing: {aoc_dir}")
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

    aoc_images = sorted(path for path in aoc_dir.glob("*.img") if path.is_file())
    prepared_aoc = {item["name"]: item for item in prep["aoc_images"]}
    if len(aoc_images) != prep["aoc_count"] or {path.name for path in aoc_images} != set(prepared_aoc):
        fail("Restored AOC directory does not contain the same unique-title-ID images as the Colab manifest.")
    handoff_aoc = ((prepared.get("game_data") or {}).get("aoc") or [])
    if len(handoff_aoc) != prep["aoc_count"] or {item.get("name") for item in handoff_aoc} != set(prepared_aoc):
        fail("Drive handoff AOC records do not match the unique-title-ID Colab AOC images.")
    for image in aoc_images:
        meta = prepared_aoc[image.name]
        drive_meta = next((item for item in handoff_aoc if item.get("name") == image.name), None)
        if (not drive_meta or image.stat().st_size != int(meta["size"])
                or image.stat().st_size != int(drive_meta.get("size", -1))
                or sha256_file(image) != meta["sha256"]
                or meta["sha256"] != drive_meta.get("sha256")
                or drive_meta.get("title_id") != meta.get("title_id")
                or drive_meta.get("aoc_index") != meta.get("aoc_index")):
            fail(f"DLC AOC SHA-256/size/Title-ID mismatch: {image.name}.")
    if prepared.get("aoc_dir") != str(aoc_dir) or prepared.get("aoc_count") != prep["aoc_count"]:
        fail("Actions input does not point to the restored Drive AOC directory with the derived image count.")

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
    return profile, version_dir, romfs, identity, aoc_dir, aoc_images, patched, prep, modules

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--prepared-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        fail("Mugiwara4iOS Route C must run on macOS ARM64.")
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
    profile, version_dir, romfs, romfs_id, aoc_dir, aoc_images, patched, prep, modules = validate_workspace(
        prepared, work, nx, builder, game_profiles)

    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(parents=True, exist_ok=True)
    (work / "ipa").mkdir(parents=True, exist_ok=True)
    py = sys.executable
    env = builder.tool_env()
    env.setdefault("USER", os.environ.get("USER") or "runner")
    env.update({"DM_GAME": TITLE_ID, "DM_GAMES_DIR": str(profile_parent),
                "DM_GAMES_FIRST": "1", "DM_ROOT": str(work),
                "WORK": str(work / "tmp"), "IOS_PULL": "1"})
    builder.configure_dotnet(env)
    xlate = engine / "dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate"
    builder.PROG.mode = "lines"
    builder.PROG.plan(10)
    try:
        print("[Mugiwara4iOS] Checking the pinned Xcode/iOS SDK, translator and Metal toolchain...", flush=True)
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
                fail("One Piece: Pirate Warriors 4's provisional heap check requires the macOS ARM64 host.")
            print("[Mugiwara4iOS] Measuring the provisional heap and guest memory split on the Mac host...", flush=True)
            builder.PROG.add(1)
            profile = builder.heap_check(engine, version_dir, patched, work, env, logs, profile)
        if (builder.HEAP_CHECK and pg.has_va(version_dir / "ExeFS")
                and not builder.region_checked(profile, patched)):
            if not builder.apple_silicon():
                fail("One Piece: Pirate Warriors 4's virtual-address region check requires the macOS ARM64 host.")
            print("[Mugiwara4iOS] Measuring guest virtual-address region usage against the iPhone alias budget...", flush=True)
            builder.PROG.add(1)
            profile = builder.region_check(engine, version_dir, patched, work, env, logs, profile)
        profile = game_profiles.load(TITLE_ID)
        if profile.dir.resolve() != (work / "profile" / TITLE_ID).resolve():
            fail("The Mac bring-up selected a profile other than the One Piece: Pirate Warriors 4 workspace profile.")

        romfs_source = builder.rfs.source(version_dir)
        facts = pg.build_sources(version_dir / "ExeFS", romfs_source, modules)
        if facts["graphics"][0] != prep["graphics_api"]:
            fail(f"Graphics API differs from Colab: {facts['graphics'][0]} != {prep['graphics_api']}.")
        actual_flags = {key: bool(facts.get(key, (False, ""))[0])
                        for key in ("ue_decode", "oodle_packs", "ue_legacy",
                                    "glslc_capture", "vk_capture", "gl_capture")}
        # Mac re-check of the Colab shader-source decision.
        if actual_flags != prep["shader_source_flags"]:
            fail(f"Shader-source flags differ between Colab and macOS: {actual_flags} != {prep['shader_source_flags']}.")
        actual_reasons = {key: str(facts[key][1]) for key in actual_flags if key in facts}
        if actual_reasons != prep["shader_source_reasons"]:
            fail("Shader-source evidence/reasons differ between Colab and macOS.")

        observed_glslc = None
        shader_dirs = {prepared["package_version"]: version_dir}
        if actual_flags["glslc_capture"]:
            print("[Mugiwara4iOS] Capturing runtime GLSLC shaders with NXNative's Mac ARM64 host...", flush=True)
            observed_glslc = builder.capture_glslc(
                engine, shader_dirs, prepared["package_version"], patched, work, env, logs, profile)

        if actual_flags["ue_decode"]:
            print("[Mugiwara4iOS] NXNative detected Unreal shader archives; decoding on Mac ARM64...", flush=True)
            builder.decode_ue_shaders(engine, shader_dirs,
                prepared["package_version"], patched, work, env, logs, profile)
            decoded_dir = version_dir / "ue_shaders"
            decoded = sorted(decoded_dir.glob("*.ushaderbytecode")) if decoded_dir.is_dir() else []
            if not decoded:
                fail("UE shader decode did not produce .ushaderbytecode archives.")

        need_oodle_host = bool(actual_flags["oodle_packs"] or actual_flags["ue_legacy"])
        oodle = None
        if need_oodle_host:
            print("[Mugiwara4iOS] Oodle/LZ5 is required by the survey; building the Mac ARM64 helper host...", flush=True)
            oodle = lambda: {
                "DM_OODLE_HOST": str(builder.build_mac_host(engine, work / "tools" / "dmhost", env, logs, profile)),
                "DM_OODLE_MODULES": str(patched),
            }
        else:
            print("[Mugiwara4iOS] No game-owned Oodle path detected; helper host is skipped.", flush=True)

        shader_package = work / "shader" / "pkg"
        package_key = builder.split_shaders(
            py, engine, [romfs_source], [version_dir / "ExeFS" / "main"],
            shader_package, env, logs, profile, provisional=True, oodle=oodle, dlc_roms=aoc_images)
        if observed_glslc is not None:
            builder.check_glslc_coverage(observed_glslc, profile)
        if not isinstance(package_key, str) or not re.fullmatch(r"[0-9a-f]{64}", package_key):
            fail("NXNative shader split did not return a valid SHA-256 package key.")
        if builder.package_key(shader_package) != package_key:
            fail("Shader package content key does not match the split result.")
        shader_map = validate_shader_map(profile)
        print(f"[Mugiwara4iOS] Shader map generated: {shader_map} ({shader_map.stat().st_size:,} bytes).", flush=True)

        gpu_selection = builder.ios_gpus("none", profile)
        pull = builder.ios_wants_pulling(profile, gpu_selection, False, env)
        print(f"[Mugiwara4iOS] Compiling iOS Metal libraries; pulling libraries: {'yes' if pull else 'no'}...", flush=True)
        ios_msl = builder.build_shaders(
            py, engine, work / "shader", xlate, env, logs, profile,
            pkg_key=package_key, mac=False, seen=None, pull=pull)
        chain_lib = ios_msl / f"b-{actual_chain}"
        chain_img = Path(str(chain_lib) + ".img")
        if not (chain_lib.is_dir() or chain_img.is_file()):
            fail(f"iOS Metal shader library is missing: {chain_lib}(.img).")
        table_stamp = validate_table_stamp(profile, ios_msl, actual_chain)
        print("[Mugiwara4iOS] c1_full.tsv, cb_extent.tsv and Metal chain input stamp all verified.", flush=True)

        jit_image = None
        if prep["jit_required"]:
            print("[Mugiwara4iOS] NXNative detected nn::jit: capturing the plugin output on the Mac and compiling its static iOS AOT image (the iPhone runs no JIT compiler)...", flush=True)
            builder.PROG.add(1)
            jit_image = builder.capture_jit(py, engine, version_dir, patched, work, env, logs, profile)
            for name in ("jit.img", "jit.tsv", "jit.out"):
                artifact = jit_image / name
                if not artifact.is_file() or artifact.stat().st_size == 0:
                    fail(f"NXNative nn::jit AOT capture is incomplete; missing {artifact}.")
            print(f"[Mugiwara4iOS] Static nn::jit image ready for DmGame.framework: {jit_image / 'jit.img'}", flush=True)

        control = builder.languages_control(version_dir)
        display_name = nacp.name(control) or profile.get("name") or "ONE PIECE: PIRATE WARRIORS 4"
        display_version = nacp.version(version_dir / "control.nacp")
        if display_version != prep["display_version"] or display_version != "1.8.7":
            fail(f"Mac NACP version changed after Colab preparation: expected {prep['display_version']}, got {display_version!r}.")
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
        print("[Mugiwara4iOS] Building DmGame.framework through NXNative DM_FRAMEWORK_ONLY; RomFS stays external.", flush=True)
        run(["bash", str(engine / "dm/ios/tools/build_ipa.sh")], cwd=engine, env=ipa_env)

        framework_name = f"DmGame{TITLE_ID}.framework"
        framework = framework_root / framework_name
        manifest_path = framework / "game.manifest.json"
        if not manifest_path.is_file():
            fail(f"NXNative framework manifest is missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        executable_name = manifest.get("framework_executable", "")
        if str(manifest.get("title_id", "")).upper() != TITLE_ID:
            fail("Framework manifest Title ID does not match One Piece: Pirate Warriors 4.")
        if manifest.get("framework") != framework_name or executable_name != framework_name.removesuffix(".framework"):
            fail("Framework name/executable does not match the One Piece: Pirate Warriors 4 Title ID.")
        if manifest.get("chain") != f"b-{actual_chain}":
            fail("Framework manifest shader chain differs from the compiled Metal chain.")
        for rel in (executable_name, "profile.tsv", "dm/shader_map.tsv", "dm/c1_full.tsv", "dm/cb_extent.tsv"):
            if not (framework / rel).is_file():
                fail(f"Framework is missing required Route C component {rel}.")
        if not (framework / "msl" / f"b-{actual_chain}.img").is_file():
            if not (framework / "msl" / f"b-{actual_chain}").is_dir():
                fail("Framework does not contain the iOS Metal library for the verified chain.")
        jit_embedded = False
        if prep["jit_required"]:
            executable = framework / executable_name
            sections = subprocess.run(["otool", "-l", str(executable)],
                capture_output=True, text=True, check=False)
            if sections.returncode != 0:
                fail(f"Could not inspect the built framework Mach-O for its static nn::jit image: {sections.stderr[-1000:]}")
            jit_embedded = "sectname __dm_jit" in sections.stdout
            if not jit_embedded:
                fail("NXNative detected nn::jit and captured its AOT image, but the DmGame.framework executable does not contain __TEXT,__dm_jit.")
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
            "DM_BUNDLE_ID": "org.nxnative.mugiwara4ios",
            "DM_APP_VERSION": display_version, "DM_TEAM_ID": "0000000000",
            "DM_XCODE_DERIVED_DATA": str(shell_dd), "FONT_PY": py,
            "STD_FONT": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        })
        print("[Mugiwara4iOS] Building the NX2Apple Shared Shell around DmGame.framework...", flush=True)
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

        ipa = output / "Mugiwara4iOS.ipa"
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
            "jit_required": prep["jit_required"],
            "jit_image_embedded": jit_embedded,
            "runtime_jit": False,
            "shader_source_flags": actual_flags, "shader_source_audit": prep["shader_source_audit"],
            "shader_chain": actual_chain, "shader_package_key": package_key,
            "metal_validation": table_stamp,
            "framework": framework_name, "ipa": ipa.name, "ipa_size_bytes": ipa.stat().st_size,
            "pipeline": [
                "Colab URL download and NSP/XCI validation",
                "NXNative metadata scan and One Piece: Pirate Warriors 4 provisional profile",
                "NXNative ARM64 rewrite and fixup audit",
                "Drive workspace/RomFS split and all 44 external DLC AOC SHA-256 validations",
                "GitHub Actions macOS ARM64 conditional GLSLC/UE/Oodle processing",
                "engine-detected shader split and profile shader table generation",
                "iOS Metal compile, c1_full/cb_extent and chain/input stamp validation",
                "conditional nn::jit Mac capture and static AOT image embedding (iPhone runtime JIT disabled)",
                "DmGame.framework build", "NX2Apple Shared Shell build",
                "ad-hoc signature and thin IPA packaging",
            ],
            "external_game_data": {
                "drive_folder_url": (prepared.get("game_data") or {}).get("folder_url"),
                "romfs_size_bytes": romfs.stat().st_size,
                "romfs_sha256": sha256_file(romfs),
                "aoc_count": len(aoc_images),
                "aoc_images": [{"name": image.name, "size_bytes": image.stat().st_size,
                                "sha256": sha256_file(image)} for image in aoc_images],
                "layout": f"games/{TITLE_ID.lower()}/romfs.img + games/{TITLE_ID.lower()}/aoc/",
            },
            "ipa_contains_romfs": False, "ipa_contains_aoc": False, "ipa_contains_nsp": False,
            "ipa_contains_xci": False, "ipa_contains_prod_keys": False,
            "pipeline_archive": {"included": False, "gpu": "none",
                "reason": "No offline MTL4 PSO archive is embedded; device-side pipeline creation remains available."},
            "signature": "ad-hoc; sideloading re-sign may be required",
            "entitlement": "com.apple.developer.kernel.increased-memory-limit",
            "runtime_validation": "Not performed by this build job; install and test on the target iPhone after IPA delivery.",
        }
        (output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        print(f"[Mugiwara4iOS] IPA complete: {ipa} ({ipa.stat().st_size:,} bytes).", flush=True)
    finally:
        try:
            builder.PROG.close(ok=True)
        except Exception:
            pass

if __name__ == "__main__":
    main()
