#!/usr/bin/env python3
"""Linux/Colab preparation for the BOTW Link2iOS Route C pipeline."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

TITLE_ID = "01007EF00011E000"
PACKAGE_VERSION = "v1114112"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"


class PreparedBoundary(Exception):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit("[Link2iOS] ERROR: " + message)


def load_builder(engine: Path):
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    require(script.is_file(), f"NXNative builder not found: {script}")
    for path in (engine / "dm/tools", engine / "dm/games", engine / "scripts"):
        sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location("link2ios_nxnative_builder", script)
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


def run_preparation(args) -> dict:
    nx = args.nx2apple_root.resolve()
    engine = nx / "engine"
    nsp_dir = args.nsp_dir.resolve()
    keys = args.keys.resolve()
    work = args.work_dir.resolve()

    require(nsp_dir.is_dir(), f"game package input directory does not exist: {nsp_dir}")
    require(keys.is_file(), "prod.keys was not downloaded")
    pin = (nx / ".upstream-ref").read_text(encoding="utf-8").strip()
    require(pin == ENGINE_PIN, f"unexpected NXNative pin: {pin}")

    module = load_builder(engine)
    check_linux_prerequisites()
    package_files = module.files_with_suffix(nsp_dir, ".xci", ".nsp")
    xci_files = [path for path in package_files if path.suffix.lower() == ".xci"]
    nsp_files = [path for path in package_files if path.suffix.lower() == ".nsp"]
    require(len(xci_files) == 1,
            f"expected exactly one BOTW base XCI, found {len(xci_files)}")
    require(len(nsp_files) == 3,
            f"expected exactly three NSPs (one update plus two DLCs), found {len(nsp_files)}")
    for path in package_files:
        require(module.is_package(path),
                f"invalid Switch package header in {path.name}; expected XCI HEAD or NSP PFS0")

    import game as game_profiles
    profile = game_profiles.by_title(int(TITLE_ID, 16))
    require(profile is not None, f"pinned NXNative engine has no registered profile for {TITLE_ID}")
    registered_package = str(profile.get("package") or "")
    require(registered_package == PACKAGE_VERSION,
            f"BOTW profile expects {PACKAGE_VERSION}, not {registered_package or 'unknown'}")

    original_run = module.run
    original_split = module.split_shaders
    split_result = {}

    def intercept_final_build(command, log=None, *pos, **kw):
        cmd = [str(x) for x in command] if isinstance(command, (list, tuple)) else [str(command)]
        normalized = [x.replace("\\", "/") for x in cmd]
        if any(x.endswith("dm/ios/tools/build_ipa.sh") for x in normalized):
            print("[Link2iOS] Linux stages complete; stopping before Xcode/Metal framework compilation.")
            raise PreparedBoundary()
        return original_run(command, log, *pos, **kw)

    def split_without_apple_host(*pos, **kw):
        # split_shaders(..., own, oodle, dlc_roms, ...): the decoder is positional arg 9.
        oodle = kw.get("oodle")
        if oodle is None and len(pos) > 9:
            oodle = pos[9]
        require(oodle is None,
                "BOTW shader split requested an Oodle/LZ5 decoder from the Apple-silicon Mac host; Colab cannot substitute it.")
        key = original_split(*pos, **kw)
        split_result["key"] = key
        return key

    def defer_ios_metal(py, repo_path, shader_root, *pos, **kw):
        out = Path(shader_root) / "ios"
        out.mkdir(parents=True, exist_ok=True)
        print("[Link2iOS] NVN package/tables prepared; iOS Metal compilation is deferred to macOS.")
        return out

    def unsupported_capture(*pos, **kw):
        raise module.BuildError(
            "this BOTW build unexpectedly requested Mac-host runtime shader/JIT capture; "
            "the Colab stage refuses to guess generated shader output"
        )

    module.check_prereqs = lambda *a, **k: check_linux_prerequisites()
    module.check_metal = lambda *a, **k: print("[Link2iOS] Apple Metal toolchain deferred to macOS.")
    module.build_shaders = defer_ios_metal
    module.split_shaders = split_without_apple_host
    module.run = intercept_final_build
    module.HEAP_CHECK = False
    for name in ("capture_glslc", "capture_shaders", "decode_ue_shaders",
                 "capture_jit", "build_vk_shaders", "build_gl_shaders"):
        if hasattr(module, name):
            setattr(module, name, unsupported_capture)

    work.mkdir(parents=True, exist_ok=True)
    framework_out = work / "shell-framework"
    argv = [
        str(nsp_dir), "-k", str(keys), "--title-id", TITLE_ID,
        "--package", PACKAGE_VERSION, "--work-dir", str(work),
        "--shell-framework", str(framework_out), "--keep-extracted",
        "--no-heap-check", "--progress", "lines", "--gpu", "none",
    ]
    parsed = module.parse_args(argv)
    try:
        module.main(parsed)
        raise SystemExit("[Link2iOS] Builder returned without reaching the expected macOS-only boundary.")
    except PreparedBoundary:
        pass
    finally:
        try:
            module.PROG.close(ok=True)
        except Exception:
            pass

    version_dir = work / "extract" / PACKAGE_VERSION
    exefs = version_dir / "ExeFS"
    romfs = version_dir / "RomFS.img"
    romfs_id = version_dir / "RomFS.img.id"
    patched = work / f"patched_{PACKAGE_VERSION}"
    shader_pkg = work / "shader" / "pkg"
    require(romfs.is_file(), f"extracted BOTW RomFS image not found: {romfs}")
    require(romfs_id.is_file(), f"RomFS identity sidecar from NX2Apple patch 0087 is missing: {romfs_id}")
    require((exefs / "main").is_file(), "extracted ExeFS/main is missing")
    require(patched.is_dir(), f"rewritten module directory missing: {patched}")
    modules = profile.modules_in(exefs)
    require({"main", "subsdk0", "sdk"}.issubset(set(modules)),
            f"BOTW ExeFS modules are incomplete: {modules}")
    for name in modules:
        require((patched / f"{name}.patched.bin").is_file(), f"rewritten module is missing: {name}")
        require((patched / f"{name}.fixups.tsv").is_file(), f"rewrite fixup table is missing: {name}")
    require(shader_pkg.is_dir(), "offline NVN shader package is missing")
    shader_key = split_result.get("key")
    require(isinstance(shader_key, str) and re.fullmatch(r"[0-9a-f]{64}", shader_key),
            "NXNative did not return a reusable shader-package content key; refusing a Mac-side shader resplit")
    shader_chain = module.chain_of(engine)
    require(bool(shader_chain), "NXNative shader chain header is missing after the Linux preparation")
    aoc = sorted((work / "aoc").glob("*.img")) if (work / "aoc").is_dir() else []
    expected_aoc = {"1.img", "2.img"}
    actual_aoc = {path.name for path in aoc}
    require(
        actual_aoc == expected_aoc and all(path.stat().st_size > 0 for path in aoc),
        "BOTW 1.9.0 requires both NXNative AOC images 1.img (01007EF00011F001) "
        f"and 2.img (01007EF00011F002); found {sorted(actual_aoc)}.",
    )

    result = {
        "format": 1,
        "project": "Link2iOS",
        "title_id": TITLE_ID,
        "package_version": PACKAGE_VERSION,
        "nx2apple_tag": "v1.3.1-rc2",
        "engine_pin": pin,
        "input_package_count": len(package_files),
        "input_xci_count": len(xci_files),
        "input_nsp_count": len(nsp_files),
        "profile_package": registered_package,
        "modules": modules,
        "shader_package_key": shader_key,
        "shader_chain": shader_chain,
        "romfs_relative_path": f"extract/{PACKAGE_VERSION}/RomFS.img",
        "romfs_id_relative_path": f"extract/{PACKAGE_VERSION}/RomFS.img.id",
        "aoc_relative_dir": "aoc",
        "aoc_title_ids": {
            "1.img": "01007EF00011F001",
            "2.img": "01007EF00011F002",
        },
        "dlc_present": True,
        "prepared_stages": [
            "nxnative_build_ipa_from_nsp_scan_nsps",
            "nx_extract_base_plus_update_to_v1114112",
            "nx_extract_each_dlc_to_aoc_1_and_2",
            "romfs_image_and_identity",
            "aarch64_module_rewrite",
            "nvn_offline_shader_split",
            "profile_shader_table_validation",
        ],
        "deferred_stages": [
            "ios_metal_shader_compile", "metal_pipeline_base_build",
            "game_framework_build", "shared_shell_xcode_build", "adhoc_sign_and_ipa_pack",
        ],
        "romfs_size": romfs.stat().st_size,
        "aoc_images": [{"name": p.name, "size": p.stat().st_size} for p in aoc],
    }
    (work / "link2ios-linux-prep.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--nsp-dir", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    run_preparation(parser.parse_args())


if __name__ == "__main__":
    main()
