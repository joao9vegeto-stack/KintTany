#!/usr/bin/env python3
"""Linux/Colab preparation for the DMC2 Dante2iOS Route C pipeline."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

TITLE_ID = "01007CF00D5BA000"
PACKAGE_VERSION = "v0"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"


class PreparedBoundary(Exception):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit("[Dante2iOS] ERROR: " + message)


def load_builder(engine: Path):
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    require(script.is_file(), f"NXNative builder not found: {script}")
    for path in (engine / "dm/tools", engine / "dm/games", engine / "scripts"):
        sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location("dante2ios_nxnative_builder", script)
    require(spec is not None and spec.loader is not None, "could not load NXNative builder")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_linux_prerequisites() -> None:
    require(sys.platform.startswith("linux"), "this stage must run on Google Colab/Linux")
    require(sys.version_info >= (3, 12), "Python 3.12 or newer is required")
    missing = []
    for name in ("lz4.block", "capstone", "fontTools", "zbic", "backports.zstd"):
        try:
            __import__(name)
        except Exception:
            missing.append(name)
    require(not missing, "missing Python modules: " + ", ".join(missing))
    for executable in ("git", "zstd", "dotnet"):
        require(shutil.which(executable) is not None, f"required executable not found: {executable}")



def ensure_linux_native_extractor(engine: Path, cache_root: Path, module) -> Path:
    """Publish the repo's real LibHac nx_extract for Linux; the committed binary is macOS-only.

    Never replace engine/dm/tools/nx_extract_bin/nx_extract: it is the locked
    universal Mach-O needed later by the Apple GitHub Actions build.
    """
    arch = platform.machine().lower()
    runtime_id = {"x86_64": "linux-x64", "amd64": "linux-x64",
                  "aarch64": "linux-arm64", "arm64": "linux-arm64"}.get(arch)
    require(runtime_id is not None, f"unsupported Linux CPU architecture: {arch}")
    expected_sha = module.nx_extract_source_sha(engine)
    target = (cache_root / "native-tools" / runtime_id / expected_sha / "nx_extract")
    cache_root.mkdir(parents=True, exist_ok=True)

    def check_extractor(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            status = subprocess.run([str(path), "--source-sha"], capture_output=True,
                                    text=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            return False
        return status.returncode == 0 and status.stdout.strip() == expected_sha

    if check_extractor(target):
        print(f"[Dante2iOS] Reusing verified Linux nx_extract: {target}", flush=True)
        return target

    require(shutil.which("dotnet") is not None, "dotnet 10 SDK is missing")
    for exe in ("clang", "gcc"):
        require(shutil.which(exe) is not None, f"NativeAOT requires {exe}; install Linux dependencies")
    project = engine / "dm" / "tools" / "nx_extract" / "nx_extract.csproj"
    require(project.is_file(), f"nx_extract C# project is missing: {project}")
    target_dir = target.parent
    output_dir = target_dir / "publish"
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "dotnet", "publish", str(project), "--configuration", "Release",
        "--runtime", runtime_id, "--self-contained", "true",
        "--nologo", "--verbosity", "minimal",
        "--artifacts-path", str(target_dir / "artifacts"),
        "--output", str(output_dir),
    ]
    print(f"[Dante2iOS] Building real NXNative LibHac nx_extract as Linux NativeAOT "
          f"({runtime_id}, source {expected_sha}); keeping the macOS binary intact.", flush=True)
    log_file = target_dir / "dotnet-publish.log"
    with log_file.open("w", encoding="utf-8") as log:
        proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                              text=True, check=False)
    if proc.returncode:
        tail = log_file.read_text(encoding="utf-8", errors="replace")[-6500:]
        require(False, f"Linux NativeAOT publish failed ({proc.returncode}), "
                f"log {log_file}:\\n{tail}")
    built = output_dir / "nx_extract"
    require(check_extractor(built),
            f"Linux nx_extract did not run with the expected embedded source hash "
            f"{expected_sha}; see {log_file}")
    # Reuse an already-verified artifact on next run. The temporary binary
    # is never pushed to GitHub, does not alter the macOS engine, and is
    # independent of NSP contents / secrets.
    import os
    os.replace(built, target)
    require(check_extractor(target), f"installed Linux nx_extract is invalid: {target}")
    print(f"[Dante2iOS] Linux nx_extract passed --source-sha: {expected_sha}", flush=True)
    return target


def run_preparation(args) -> dict:
    """Run nxnative's real NSP scan, provisional profile survey, extraction, rewrite and offline shader phase."""
    nx, nsp_dir, keys, work = (args.nx2apple_root.resolve(), args.nsp_dir.resolve(),
                               args.keys.resolve(), args.work_dir.resolve())
    engine = nx / "engine"
    require((nx / ".upstream-ref").read_text().strip() == ENGINE_PIN, "mismatched engine pin")
    require(nsp_dir.is_dir() and keys.is_file(), "missing base NSP or prod.keys")
    module = load_builder(engine)
    check_linux_prerequisites()
    linux_nx_extract = ensure_linux_native_extractor(engine, nx.parent, module)
    # NXNative's builder resolves repo / NX_EXTRACT in its own module.
    # An absolute Linux path replaces only the executable selected here.
    # The committed universal macOS executable remains untouched for Actions.
    module.NX_EXTRACT = str(linux_nx_extract)
    files = module.files_with_suffix(nsp_dir, ".nsp", ".xci")
    require(len(files) == 1 and files[0].suffix.lower() == ".nsp",
            f"expected one base NSP only, found {[p.name for p in files]}")
    require(module.is_package(files[0]), "base NSP must have a valid PFS0 header")
    import game as game_profiles

    # Colab/Linux has no Xcode/Metal; defer only those operations. Never fake an
    # extraction, a rewrite, a shader split or a required capture.
    original_run, original_split = module.run, module.split_shaders
    split = {}
    class FinishedLinux(Exception):
        pass
    def intercepted_run(command, log=None, *extra, **kw):
        parts = [str(x) for x in command] if isinstance(command, (tuple, list)) else [str(command)]
        if any(x.replace("\\", "/").endswith("dm/ios/tools/build_ipa.sh") for x in parts):
            print("[Dante2iOS] Preparação Linux concluída; compilação Xcode reservada ao Actions.")
            raise FinishedLinux()
        return original_run(command, log, *extra, **kw)
    def split_record(*a, **kw):
        oodle = kw.get("oodle", a[9] if len(a) > 9 else None)
        require(oodle is None, "DMC2 needs a Mac-host Oodle shader decoder; this Linux route must not fake its results.")
        key = original_split(*a, **kw)
        split["key"] = key
        return key
    def defer_metal(*a, **kw):
        out = work / "shader" / "ios"
        out.mkdir(parents=True, exist_ok=True)
        print("[Dante2iOS] Tradução Metal/iOS adiada para Actions.")
        return out
    def required_host_capture(*a, **kw):
        raise module.BuildError(
            "DMC2 requires a runtime shader/JIT/Unreal capture on Apple Silicon. "
            "The prepared Linux route cannot claim a successful offline capture; "
            "inspect the provisional survey and implement the Mac phase for this graphics backend.")
    module.check_prereqs = lambda *a, **kw: check_linux_prerequisites()
    module.check_metal = lambda *a, **kw: None
    module.run = intercepted_run
    module.split_shaders = split_record
    module.build_shaders = defer_metal
    module.build_vk_shaders = defer_metal
    module.build_gl_shaders = defer_metal
    for name in ("capture_glslc", "capture_shaders", "decode_ue_shaders", "capture_jit"):
        if hasattr(module, name):
            setattr(module, name, required_host_capture)
    module.HEAP_CHECK = False
    work.mkdir(parents=True, exist_ok=True)
    parsed = module.parse_args([
        str(nsp_dir), "-k", str(keys), "--title-id", TITLE_ID,
        "--package", PACKAGE_VERSION, "--work-dir", str(work),
        "--shell-framework", str(work / "shell-framework"),
        "--keep-extracted", "--romfs", "separate",
        "--no-heap-check", "--progress", "lines", "--gpu", "none",
    ])
    try:
        module.main(parsed)
        raise SystemExit("[Dante2iOS] builder ended without entering the Xcode-only boundary.")
    except FinishedLinux:
        pass
    finally:
        try:
            module.PROG.close(ok=True)
        except Exception:
            pass

    version_dir = work / "extract" / PACKAGE_VERSION
    exefs = version_dir / "ExeFS"
    romfs, identity = version_dir / "RomFS.img", version_dir / "RomFS.img.id"
    patched = work / f"patched_{PACKAGE_VERSION}"
    require(romfs.is_file() and romfs.stat().st_size > 0, "DMC2 RomFS was not extracted")
    require(identity.is_file(), "RomFS.img.id provenance is missing")
    require((exefs / "main").is_file() and (exefs / "main.npdm").is_file(),
            "DMC2 ExeFS/main or main.npdm is absent")
    require((work / "profile" / TITLE_ID / "game.tsv").is_file()
            or game_profiles.by_title(int(TITLE_ID, 16)) is not None,
            "neither provisional nor registered DMC2 profile was produced")
    profile = game_profiles.load(TITLE_ID)
    modules = profile.modules_in(exefs)
    require("main" in modules and (patched / "main.patched.bin").is_file(),
            "rewritten DMC2 main was not produced")
    for name in modules:
        require((patched / f"{name}.patched.bin").is_file()
                and (patched / f"{name}.fixups.tsv").is_file(),
                f"missing rewrite output for {name}")
    sources = module.build_sources(engine, version_dir, modules)
    gfx = sources["graphics"][0]
    require(gfx in ("nvn", "gl", "vulkan"), f"unsupported graphics backend: {gfx}")
    if gfx == "nvn":
        key = split.get("key")
        require(isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key),
                "NVN shader split did not produce a reusable package key")
        require((work / "shader" / "pkg").is_dir(), "offline NVN shader package missing")
    else:
        key = None
    require(not list((work / "aoc").glob("*.img")) if (work / "aoc").is_dir() else True,
            "base-only DMC2 unexpectedly produced DLC AOC images")
    result = {
        "format": 1, "project": "Dante2iOS", "branch": "Dante2iOS",
        "title_id": TITLE_ID, "package_version": PACKAGE_VERSION,
        "source_ref": "Dante2iOS", "engine_pin": ENGINE_PIN,
        "input_package_count": 1, "input_nsp_count": 1, "input_update_count": 0,
        "input_dlc_count": 0, "provisional": (work / "profile" / TITLE_ID / "game.tsv").is_file(),
        "profile_relative_dir": "profile",
        "graphics": gfx, "modules": modules,
        "shader_package_key": key, "shader_chain": module.chain_of(engine),
        "romfs_relative_path": f"extract/{PACKAGE_VERSION}/RomFS.img",
        "romfs_id_relative_path": f"extract/{PACKAGE_VERSION}/RomFS.img.id",
        "aoc_images": [], "aoc_title_ids": {}, "dlc_present": False,
        "romfs_size": romfs.stat().st_size,
        "prepared_stages": ["real_content_metadata_scan", "provisional_profile_survey_if_required",
            "base_v0_romfs_extract", "aarch64_rewrite",
            "offline_nvn_shader_split" if gfx == "nvn" else "gl_vk_shader_translation_deferred"],
        "deferred_stages": ["ios_metal_shader_compile", "game_framework_build",
            "shared_shell_xcode_build", "adhoc_sign_and_ipa_pack"],
        "limitations": ["provisional_heap_and_region_checks_skipped_on_linux"],
    }
    (work / "dante2ios-linux-prep.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--nsp-dir", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    print(json.dumps(run_preparation(parser.parse_args()), indent=2))


if __name__ == "__main__":
    main()
