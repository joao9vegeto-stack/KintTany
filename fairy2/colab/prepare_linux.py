#!/usr/bin/env python3
"""Linux/Colab preparation for the Fairy Tail 2 Fairy2iOS Route C pipeline."""
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
import threading
import time
from pathlib import Path

TITLE_ID = "0100B9801F872000"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"


class PreparedBoundary(Exception):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit("[Fairy2iOS] ERROR: " + message)


def load_builder(engine: Path):
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    require(script.is_file(), f"NXNative builder not found: {script}")
    for path in (engine / "dm/tools", engine / "dm/games", engine / "scripts"):
        sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location("fairy2_nxnative_builder", script)
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
        print(f"[Fairy2iOS] Reusing verified Linux nx_extract: {target}", flush=True)
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
    print(f"[Fairy2iOS] Building real NXNative LibHac nx_extract as Linux NativeAOT "
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
    print(f"[Fairy2iOS] Linux nx_extract passed --source-sha: {expected_sha}", flush=True)
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
    # Guard the real NXNative rewrite BEFORE launching its resource-intensive
    # AArch64 workers; reuses validated completed outputs from a SIGKILL run.
    import rewrite_guard
    rewrite_guard.install(module)
    linux_nx_extract = ensure_linux_native_extractor(engine, nx.parent, module)
    # NXNative's builder resolves repo / NX_EXTRACT in its own module.
    # An absolute Linux path replaces only the executable selected here.
    # The committed universal macOS executable remains untouched for Actions.
    module.NX_EXTRACT = str(linux_nx_extract)
    files = module.files_with_suffix(nsp_dir, ".nsp", ".xci")
    require(len(files) == 18 and all(p.suffix.lower() == ".nsp" and module.is_package(p) for p in files),
            f"expected 18 base/update/DLC NSPs, found {[p.name for p in files]}")
    # Verify both content metas using the real NXNative/LibHac extractor.
    with module.package_reader(engine, keys, module.tool_env()) as packages:
        app, family = module.scan_nsps(nsp_dir, packages.contents, int(TITLE_ID, 16))
        packages.check_keys(family)
    require(app == int(TITLE_ID, 16) and family["base"] is not None,
            "base NSP Application title ID mismatch")
    require(family["base_version"] == 0 and len(family["updates"]) == 1 and len(family["dlc"]) == 16,
            "expected base v0, one update, and 16 valid DLC contents")
    update_version, update_path = family["updates"][0]
    require(isinstance(update_version, int) and update_version > 0 and update_path != family["base"],
            "update NSP content metadata is invalid")
    package_version = f"v{update_version}"
    print(f"[Fairy2iOS] Package metadata validated: base {TITLE_ID} v0 + update {package_version}", flush=True)
    import game as game_profiles
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from port_stages import source_flags, deferred_mac_stages

    # Colab/Linux has no Xcode/Metal; defer only those operations. Never fake an
    # extraction, a rewrite, a shader split or a required capture.
    original_run, original_split = module.run, module.split_shaders
    split = {}
    deferred = {"stage": None}
    ue_linux = {"completed": False}
    class FinishedLinux(Exception):
        pass
    class NeedsMacHost(Exception):
        def __init__(self, stage: str):
            super().__init__(stage)
            self.stage = stage
    def intercepted_run(command, log=None, *extra, **kw):
        parts = [str(x) for x in command] if isinstance(command, (tuple, list)) else [str(command)]
        if any(x.replace("\\", "/").endswith("dm/ios/tools/build_ipa.sh") for x in parts):
            print("[Fairy2iOS] Preparação Linux concluída; compilação Xcode reservada ao Actions.")
            raise FinishedLinux()
        return original_run(command, log, *extra, **kw)
    def split_record(*a, **kw):
        oodle = kw.get("oodle", a[9] if len(a) > 9 else None)
        if oodle is not None:
            raise NeedsMacHost("oodle_packs")
        key = original_split(*a, **kw)
        split["key"] = key
        return key
    def defer_metal(*a, **kw):
        out = work / "shader" / "ios"
        out.mkdir(parents=True, exist_ok=True)
        print("[Fairy2iOS] Tradução Metal/iOS adiada para Actions.")
        return out
    def need_mac(stage):
        def capture(*a, **kw):
            if stage == "shader_capture":
                api = kw.get("api", a[-1] if a else "")
                stage_name = {"vk": "vk_capture", "gl": "gl_capture"}.get(api)
                if stage_name is None:
                    raise module.BuildError(f"Unknown runtime shader capture backend: {api!r}")
                raise NeedsMacHost(stage_name)
            raise NeedsMacHost(stage)
        return capture

    def ue_decode_linux(repo, dirs, pkg_ver, patched, workspace, env, logs, g):
        """Use actual NXNative UE pak reader on Linux; only Oodle/IoStore needs Mac."""
        sys.path.insert(0, str(engine / "dm/gfx/tools"))
        import uepak
        for version, game_dir in dirs.items():
            target = game_dir / "ue_shaders"
            stamp = module.ue_stamp(game_dir)
            if (target / "stamp").is_file() and (target / "stamp").read_text() == stamp:
                print(f"[Fairy2iOS] UE shaders {version}: Linux decoder cache reused.", flush=True)
                continue
            rom = module.rfs.source(game_dir)
            if uepak.io_shader_tocs(str(rom)):
                raise NeedsMacHost("ue_decode")
            job = workspace / "tmp" / f"ue_linux_{version}"
            module.rmtree(job)
            try:
                listing, n_oodle = uepak.job(str(rom), str(game_dir / "ExeFS/main"), str(job), decode=None)
            except ValueError as exc:
                raise module.BuildError(f"UE shader package could not be read on Linux: {exc}") from exc
            if not listing:
                raise module.BuildError("Unreal paks contain no shader code archive; refusing an empty shader build")
            if n_oodle:
                print(f"[Fairy2iOS] Parsed UE shader archives on Linux; "
                      f"{n_oodle:,} shaders need the game's Oodle decoder on Mac.", flush=True)
                raise NeedsMacHost("ue_decode")
            out = game_dir / "ue_shaders.partial"
            module.rmtree(out)
            uepak.finish(str(job), str(out))
            (out / "stamp").write_text(stamp)
            module.swap_in(out, target)
            module.rmtree(job)
            print(f"[Fairy2iOS] Real UE LZ4/zlib decode on Linux: "
                  f"{sum(x['shaders'] for x in listing):,} shaders ({version}).", flush=True)
        ue_linux["completed"] = True

    module.check_prereqs = lambda *a, **kw: check_linux_prerequisites()
    module.check_metal = lambda *a, **kw: None
    module.run = intercepted_run
    module.split_shaders = split_record
    module.build_shaders = defer_metal
    module.build_vk_shaders = defer_metal
    module.build_gl_shaders = defer_metal
    for fn, kind in (("capture_glslc", "glslc_capture"),
                     ("capture_shaders", "shader_capture"),
                     ("capture_jit", "jit_capture")):
        if hasattr(module, fn):
            setattr(module, fn, need_mac(kind))
    if hasattr(module, "decode_ue_shaders"):
        module.decode_ue_shaders = ue_decode_linux
    module.HEAP_CHECK = False
    work.mkdir(parents=True, exist_ok=True)
    parsed = module.parse_args([
        str(nsp_dir), "-k", str(keys), "--title-id", TITLE_ID,
        "--package", package_version, "--work-dir", str(work),
        "--shell-framework", str(work / "shell-framework"),
        "--keep-extracted", "--romfs", "separate",
        "--no-heap-check", "--progress", "lines", "--gpu", "none",
    ])
    # NXNative counts fully rewritten modules, not instructions processed
    # inside an active module. Its original ETA remains frozen indefinitely
    # when no additional module finishes. Hide only stale module ETAs.
    original_eta = module.PROG._eta
    def honest_eta(stage):
        if (stage.unit == "modules" and stage.hist
                and time.time() - stage.hist[-1][0] > 90):
            return None
        return original_eta(stage)
    module.PROG._eta = honest_eta

    # Read-only health observations; they never interrupt the rewriter and
    # never change its process count, cache or CPU allocation.
    heartbeat_stop = threading.Event()
    def rewrite_heartbeat():
        while not heartbeat_stop.wait(120):
            with module.PROG.lock:
                stage = module.PROG.cur
                if not stage or stage.name != "rewrite" or stage.total is None:
                    continue
                completed, total = stage.done or 0, stage.total
            try:
                proc = subprocess.run(
                    ["ps", "-eo", "pid,stat,pcpu,pmem,etime,args"],
                    capture_output=True, text=True, check=False, timeout=15)
                active = [line.strip() for line in proc.stdout.splitlines()
                          if "patch_nso.py" in line and
                          "ps -eo" not in line]
                log_paths = sorted((work / "logs").glob("rewrite_*.log"))
                reports = []
                now = time.time()
                for log in log_paths:
                    st = log.stat()
                    reports.append(f"{log.name}={st.st_size:,}B, "
                                   f"updated {int(now - st.st_mtime)}s ago")
                print(f"[Fairy2iOS] Rewrite heartbeat: {completed}/{total} "
                      "modules finished. The counter moves only when a whole "
                      "module finishes.", flush=True)
                for line in active[:12]:
                    print("[Fairy2iOS] Active rewrite:", line, flush=True)
                if not active:
                    print("[Fairy2iOS] No patch_nso.py process found at this "
                          "snapshot; check for a finished/failed worker.", flush=True)
                if reports:
                    print("[Fairy2iOS] Rewrite logs: "
                          + " | ".join(reports[-12:]), flush=True)
            except (OSError, subprocess.SubprocessError) as exc:
                print("[Fairy2iOS] Rewrite heartbeat unavailable: "
                      + type(exc).__name__, flush=True)

    heartbeat_thread = threading.Thread(target=rewrite_heartbeat, daemon=True)
    heartbeat_thread.start()
    try:
        module.main(parsed)
        raise SystemExit("[Fairy2iOS] builder ended without entering the Xcode-only boundary.")
    except module.BuildError as exc:
        if "patch_nso.py exit code -9" in str(exc):
            print("[Fairy2iOS] SIGKILL in patch_nso.py. Possible cgroup "
                  "OOM kill; inspecting memory events:", flush=True)
            for probe in ("/sys/fs/cgroup/memory.events",
                          "/sys/fs/cgroup/memory.peak",
                          "/sys/fs/cgroup/memory.max",
                          "/proc/meminfo"):
                try:
                    data = Path(probe).read_text(errors="replace")
                    print(f"[Fairy2iOS] {probe}: "
                          + (data[:650] if probe.endswith("meminfo") else data[:2000]),
                          flush=True)
                except OSError:
                    pass
            print("[Fairy2iOS] Keep the existing /content/fairy2/work "
                  "and use the updated one-worker checkpointed rewrite. "
                  "If the main alone exceeds memory, select a Colab high-RAM "
                  "runtime; no other parallel worker can be removed.", flush=True)
        raise
    except FinishedLinux:
        pass
    except NeedsMacHost as pending:
        deferred["stage"] = pending.stage
        print(f"[Fairy2iOS] Checkpoint real: Linux extraiu/reescreveu os módulos. "
              f"Apenas {pending.stage} depende de Apple Silicon; "
              "o trabalho foi preservado para o handoff.", flush=True)
    finally:
        heartbeat_stop.set()
        try:
            module.PROG.close(ok=True)
        except Exception:
            pass

    version_dir = work / "extract" / package_version
    exefs = version_dir / "ExeFS"
    romfs, identity = version_dir / "RomFS.img", version_dir / "RomFS.img.id"
    patched = work / f"patched_{package_version}"
    require(romfs.is_file() and romfs.stat().st_size > 0, "Fairy Tail 2 RomFS was not extracted")
    require(identity.is_file(), "RomFS.img.id provenance is missing")
    require((exefs / "main").is_file() and (exefs / "main.npdm").is_file(),
            "Fairy Tail 2 ExeFS/main or main.npdm is absent")
    require((work / "profile" / TITLE_ID / "game.tsv").is_file()
            or game_profiles.by_title(int(TITLE_ID, 16)) is not None,
            "neither provisional nor registered Fairy Tail 2 profile was produced")
    profile = game_profiles.load(TITLE_ID)
    modules = profile.modules_in(exefs)
    require("main" in modules and (patched / "main.patched.bin").is_file(),
            "rewritten Fairy Tail 2 main was not produced")
    for name in modules:
        require((patched / f"{name}.patched.bin").is_file()
                and (patched / f"{name}.fixups.tsv").is_file(),
                f"missing rewrite output for {name}")
    sources = module.build_sources(engine, version_dir, modules)
    gfx = sources["graphics"][0]
    require(gfx in ("nvn", "gl", "vulkan"), f"unsupported graphics backend: {gfx}")
    flags = source_flags(sources)
    jit = bool(module.uses_jit(exefs))
    mac_stages = deferred_mac_stages(sources, jit=jit,
                                     linux_ue_complete=ue_linux["completed"])
    if bool(deferred["stage"]) != bool(mac_stages):
        require(False, f"Source-detected Mac dependencies {mac_stages} do not match "
                f"the captured Linux boundary {deferred['stage']!r}")
    key = split.get("key") if gfx == "nvn" else None
    if gfx == "nvn" and key is None:
        require(bool(mac_stages and deferred["stage"] != "jit_capture"),
                "NVN shader split was not completed and no prior Mac-only dependency explains why")
    if key is not None:
        require(re.fullmatch(r"[0-9a-f]{64}", key) is not None
                and (work / "shader" / "pkg").is_dir(),
                "Linux NVN shader split key or package is invalid")
    shader_stage = ("linux_complete" if gfx == "nvn" and key else
                    "mac_pending" if gfx == "nvn" else "metal_deferred")
    versions = list(profile.words("shader_versions"))
    if (work / "profile" / TITLE_ID / "game.tsv").exists() and package_version not in versions:
        versions.append(package_version)
    if not versions:
        versions = [package_version]
    shader_versions = sorted(set(versions))
    for ver in shader_versions:
        require((work / "extract" / ver / "ExeFS" / "main").is_file(),
                f"required shader input version {ver} is not extracted")
    print(f"[Fairy2iOS] Linux: shader_stage={shader_stage}, "
          f"Mac-only={mac_stages}, source_flags={flags}, "
          f"shader_versions={shader_versions}", flush=True)
    # Record actual output DLC images. Some DLCs may be metadata-only, without AOC.
    aoc_images = []
    for image in sorted((work / "aoc").glob("*.img")):
        require(image.is_file() and re.fullmatch(r"[A-Za-z0-9_-]+\.img", image.name)
                and image.stat().st_size > 0, f"invalid NXNative AOC image: {image}")
        aoc_images.append({"name": image.name, "size": image.stat().st_size})
    require(len(aoc_images) <= 16, "NXNative emitted more than 16 AOC images")
    result = {
        "format": 1, "project": "Fairy2iOS", "branch": "Fairy2iOS",
        "title_id": TITLE_ID, "package_version": package_version,
        "source_ref": "Fairy2iOS", "engine_pin": ENGINE_PIN,
        "input_package_count": 18, "input_nsp_count": 18, "input_update_count": 1,
        "base_content_version": 0, "update_content_version": update_version,
        "input_dlc_count": 16, "provisional": (work / "profile" / TITLE_ID / "game.tsv").is_file(),
        "profile_relative_dir": "profile",
        "graphics": gfx, "modules": modules,
        "shader_package_key": key, "shader_chain": module.chain_of(engine),
        "shader_split_stage": shader_stage, "source_capture_flags": flags,
        "mac_host_stages": mac_stages, "jit_required": jit,
        "linux_ue_decode_complete": ue_linux["completed"],
        "shader_versions": shader_versions,
        "romfs_relative_path": f"extract/{package_version}/RomFS.img",
        "romfs_id_relative_path": f"extract/{package_version}/RomFS.img.id",
        "aoc_images": aoc_images, "aoc_title_ids": {}, "dlc_present": True,
        "romfs_size": romfs.stat().st_size,
        "prepared_stages": ["real_content_metadata_scan", "provisional_profile_survey_if_required",
            "base_plus_update_romfs_merge", "aarch64_rewrite",
            "offline_nvn_shader_split" if shader_stage == "linux_complete" else
            "mac_shader_split_waiting_for_capture" if shader_stage == "mac_pending"
            else "gl_vk_shader_translation_deferred"],
        "deferred_stages": mac_stages +
            (["mac_shader_split_after_capture"] if shader_stage == "mac_pending" else []) +
            ["ios_metal_shader_compile", "game_framework_build",
            "shared_shell_xcode_build", "adhoc_sign_and_ipa_pack"],
        "limitations": ["provisional_heap_and_region_checks_skipped_on_linux"],
    }
    (work / "fairy2-linux-prep.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
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
