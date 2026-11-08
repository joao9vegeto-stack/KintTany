#!/usr/bin/env python3
"""Run NXNative's Linux-safe preparation stages and stop before Apple/Metal compilation."""
from __future__ import annotations
import argparse, importlib.util, json, shutil, sys
from pathlib import Path

class PreparedBoundary(Exception):
    pass

def require(ok, message):
    if not ok:
        raise SystemExit("[Kleo2iOS] ERROR: " + message)

def load_builder(engine):
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    require(script.is_file(), f"NXNative builder not found: {script}")
    for p in (engine / "dm/tools", engine / "dm/games", engine / "scripts"):
        sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location("kleo_nxnative_builder", script)
    require(spec is not None and spec.loader is not None, "cannot load NXNative builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def inspect_nup(engine, nup_path):
    for p in (engine / "dm/tools", engine / "dm/games", engine / "scripts"):
        sys.path.insert(0, str(p))
    import pack_nup
    import game as game_profiles
    nup = pack_nup.Nup(nup_path)
    try:
        title_id, base, updates, dlc = pack_nup.scan(nup)
    finally:
        nup.close()
    profile = game_profiles.by_title(title_id)
    require(profile is not None,
            f"no registered NXNative profile for {title_id:016X}; Linux preparation refuses to guess a profile")
    version = f"v{max(updates)}" if updates else "v0"
    print(f"[Kleo2iOS] Game: {title_id:016X}; package: {version}; DLC packages: {len(dlc)}")
    print(f"[Kleo2iOS] Registered profile: {profile.dir}")
    return f"{title_id:016X}", version

def linux_prerequisites(module, env, xlate, mac=False):
    require(sys.platform.startswith("linux"), "this preparation stage must run on Linux/Colab")
    require(sys.version_info >= (3, 12), "Python 3.12 or newer is required by NXNative")
    missing = []
    for name in ("lz4.block", "capstone", "fontTools", "zbic", "backports.zstd"):
        try:
            __import__(name)
        except Exception:
            missing.append(name)
    require(not missing, "missing Python modules: " + ", ".join(missing))
    require(shutil.which("zstd") is not None, "zstd executable missing; install the zstd package")
    module.check_capstone()
    print("[Kleo2iOS] Linux prerequisites passed; Apple SDK and Metal checks are deferred to Actions.")

def run_preparation(args):
    engine, nup, work = args.engine_root.resolve(), args.nup.resolve(), args.work_dir.resolve()
    require(nup.is_file(), f"NUP file not found: {nup}")
    require(nup.suffix.lower() == ".nup", "input must be a Switch 2 .nup container")
    require(sys.platform.startswith("linux"), "run this script in Google Colab/Linux")
    title_id, package_version = inspect_nup(engine, nup)
    module = load_builder(engine)
    original_run, original_split = module.run, module.split_shaders

    def intercept_final_build(command, log=None, *pos, **kw):
        cmd = [str(x) for x in command] if isinstance(command, (list, tuple)) else [str(command)]
        if any(x.replace("\\", "/").endswith("dm/ios/tools/build_ipa.sh") for x in cmd):
            print("[Kleo2iOS] Linux preparation complete; stopping before Apple-only compilation.")
            raise PreparedBoundary()
        return original_run(command, log, *pos, **kw)

    def split_without_mac_decoder(*pos, **kw):
        oodle = kw.get("oodle")
        if oodle is None and len(pos) > 9:
            oodle = pos[9]
        require(oodle is None,
                "shader archives require Oodle/LZ5 decoding in the Apple-silicon host; this game is not Linux-preparable")
        return original_split(*pos, **kw)

    def defer_metal(py, repo_path, shader_root, *pos, **kw):
        out = Path(shader_root) / "ios"
        out.mkdir(parents=True, exist_ok=True)
        print("[Kleo2iOS] Offline shader package/tables prepared; iOS Metal compilation is deferred to macOS.")
        return out

    def unsupported_capture(*pos, **kw):
        raise module.BuildError(
            "this game requires runtime shader/JIT capture in the Apple-silicon host; "
            "Colab cannot substitute an emulator or interpreter"
        )

    module.check_prereqs = lambda env, xlate, mac=False: linux_prerequisites(module, env, xlate, mac)
    module.check_metal = lambda *a, **k: print("[Kleo2iOS] Deferred Metal toolchain check.")
    module.build_shaders = defer_metal
    module.split_shaders = split_without_mac_decoder
    module.run = intercept_final_build
    module.HEAP_CHECK = False
    for name in ("capture_glslc", "capture_shaders", "decode_ue_shaders", "capture_jit",
                 "build_vk_shaders", "build_gl_shaders"):
        if hasattr(module, name):
            setattr(module, name, unsupported_capture)

    framework_out = work / "shell-framework"
    argv = [
        str(nup), "--work-dir", str(work), "--shell-framework", str(framework_out),
        "--keep-extracted", "--no-heap-check", "--progress", "lines",
        "--gpu", "g18p", "--out", str(work / "handoff-not-built.ipa"),
    ]
    parsed = module.parse_args(argv)
    try:
        module.main(parsed)
        raise SystemExit("[Kleo2iOS] Builder returned without reaching the expected Apple-build boundary.")
    except PreparedBoundary:
        pass
    finally:
        try:
            module.PROG.close(ok=True)
        except Exception:
            pass

    extracts = sorted((work / "extract").glob("v*/RomFS.img"))
    require(bool(extracts), f"no extracted RomFS image under {work / 'extract'}")
    patched = sorted(work.glob("patched_*"))
    require(bool(patched), "rewritten module directory was not produced")
    require(any(any(p.glob("main.patched.bin")) for p in patched), "rewritten main module is missing")
    require((work / "shader/pkg").is_dir(), "offline shader package was not produced")

    result = {
        "format": 1, "title_id": title_id, "package_version": package_version,
        "nup_name": nup.name,
        "engine_pin": (args.nx2apple_root / ".upstream-ref").read_text().strip(),
        "nx2apple_tag": "v1.3.0-rc10", "work_dir": "work",
        "prepared_stages": ["nup_scan", "romfs_extraction", "module_rewrite", "offline_shader_split"],
        "deferred_stages": ["ios_metal_shader_compile", "pipeline_archive", "game_framework_build", "shared_shell_build"],
        "romfs_images": [{"path": str(p.relative_to(work)), "size": p.stat().st_size} for p in extracts],
    }
    work.mkdir(parents=True, exist_ok=True)
    (work / "kleo-linux-prep.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-root", type=Path, required=True)
    ap.add_argument("--nx2apple-root", type=Path, required=True)
    ap.add_argument("--nup", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    run_preparation(ap.parse_args())

if __name__ == "__main__":
    main()
