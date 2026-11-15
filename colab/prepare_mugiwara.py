#!/usr/bin/env python3
"""Linux/Colab extraction, provisional-profile generation and ARM64 rewrite for One Piece: Pirate Warriors 4."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TITLE_ID = "01008FE00E2F6000"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
PROJECT = "Mugiwara4iOS"

class PreparedBoundary(Exception):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage

def fail(message: str) -> None:
    raise SystemExit("[Mugiwara4iOS] ERROR: " + message)

def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def install_linux_dependencies(root: Path) -> None:
    require(sys.platform.startswith("linux"), "Colab preparation must run on Linux.")
    require(sys.version_info >= (3, 12), "NXNative requires Python 3.12 or newer.")
    commands = {"git": "git", "zstd": "zstd", "curl": "curl", "cmake": "cmake",
                "ninja": "ninja-build", "pkg-config": "pkg-config"}
    packages = ["build-essential", "libssl-dev"]
    missing = [package for command, package in commands.items() if shutil.which(command) is None]
    def installed(name: str) -> bool:
        result = subprocess.run(["dpkg-query", "-W", "-f=$" + "{db:Status-Status}", name],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return result.returncode == 0 and result.stdout.strip() == "installed"
    missing += [name for name in packages if not installed(name)]
    missing = list(dict.fromkeys(name for name in missing if not installed(name)))
    if missing:
        print("[Mugiwara4iOS] Installing Linux dependencies: " + ", ".join(missing), flush=True)
        update = subprocess.run(["apt-get", "update", "-qq"], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        if update.returncode:
            fail("apt-get update failed: " + update.stdout[-3000:])
        result = subprocess.run(["apt-get", "install", "-y", "-qq", *missing],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.returncode:
            fail("APT package installation failed: " + result.stdout[-4000:])
    absent = [name for name in commands if shutil.which(name) is None]
    if absent:
        fail("Linux dependencies remain unavailable: " + ", ".join(absent))
    python_packages = (
        ("lz4.block", "lz4"), ("capstone", "capstone>=5,<6"),
        ("fontTools", "fonttools"), ("zbic", "zbic"),
        ("backports.zstd", "backports.zstd"), ("requests", "requests"),
        ("Crypto.Cipher", "pycryptodome"),
    )
    missing_pip = []
    for module_name, package_name in python_packages:
        try:
            if importlib.util.find_spec(module_name) is None:
                missing_pip.append(package_name)
        except (ImportError, ModuleNotFoundError, ValueError):
            missing_pip.append(package_name)
    if missing_pip:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing_pip], check=True)
    dotnet_root = Path("/content/dotnet").resolve()
    dotnet = dotnet_root / "dotnet"
    env = os.environ.copy()
    if dotnet.is_file():
        env.update({"DOTNET_ROOT": str(dotnet_root), "DOTNET_ROOT_X64": str(dotnet_root),
                    "DOTNET_HOST_PATH": str(dotnet),
                    "PATH": str(dotnet_root) + os.pathsep + env.get("PATH", "")})
    runtimes = ""
    if dotnet.is_file():
        check = subprocess.run([str(dotnet), "--list-runtimes"], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if check.returncode == 0:
            runtimes = check.stdout
    if not re.search(r"^Microsoft\.NETCore\.App\s+10\.", runtimes, re.M):
        dotnet_root.mkdir(parents=True, exist_ok=True)
        installer = root / "dotnet-install.sh"
        subprocess.run(["curl", "-fsSL", "https://dot.net/v1/dotnet-install.sh", "-o", str(installer)], check=True)
        subprocess.run(["bash", str(installer), "--channel", "10.0", "--install-dir", str(dotnet_root)], check=True)
        env = os.environ.copy()
        env.update({"DOTNET_ROOT": str(dotnet_root), "DOTNET_ROOT_X64": str(dotnet_root),
                    "DOTNET_HOST_PATH": str(dotnet),
                    "PATH": str(dotnet_root) + os.pathsep + env.get("PATH", "")})
        runtimes = subprocess.run([str(dotnet), "--list-runtimes"], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True).stdout
    require(dotnet.is_file() and re.search(r"^Microsoft\.NETCore\.App\s+10\.", runtimes, re.M),
            ".NET 10 runtime was not installed correctly.")
    os.environ.update({"DOTNET_ROOT": str(dotnet_root), "DOTNET_ROOT_X64": str(dotnet_root),
                       "DOTNET_HOST_PATH": str(dotnet),
                       "PATH": str(dotnet_root) + os.pathsep + os.environ.get("PATH", "")})
    print("[Mugiwara4iOS] Python, Linux tools and .NET 10 validated.", flush=True)

def load_builder(engine: Path):
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    require(script.is_file(), f"NXNative builder missing: {script}")
    for name in ("game", "nacp", "profile_guess", "nso", "nso_syms", "nso_asm",
                 "uepak", "uepak_extract", "nso_match", "sdk_patches",
                 "pack_nup", "pack_dump", "nx_extract", "patch_nso", "romfs"):
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    for folder in (engine / "dm/tools", engine / "dm/games", engine / "dm/gfx/tools", engine / "scripts"):
        sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("mugiwara_nxnative_builder", script)
    require(spec is not None and spec.loader is not None, "Could not load pinned NXNative build_ipa_from_nsp.py.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def install_linux_aes_compat() -> None:
    """Give NXNative's generic PAK scanner AES-256-ECB on Linux.
    
    profile_guess.build_sources() inspects Unreal PAK metadata even when the game
    is not an Unreal title. The upstream reader uses macOS CommonCrypto by default;
    this compatibility shim makes encrypted-index inspection work in Colab/Linux
    if such containers are present. It does not force an Unreal shader path.
    """
    require(sys.platform.startswith("linux"), "Linux AES compatibility is only used during Colab preparation.")
    from Crypto.Cipher import AES
    key = bytes(range(32))
    plaintext = bytes.fromhex("00112233445566778899aabbccddeeff")
    ciphertext = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")
    require(AES.new(key, AES.MODE_ECB).decrypt(ciphertext) == plaintext,
            "PyCryptodome AES-256-ECB self-test failed.")
    import uepak
    def aes_decrypt(key_bytes: bytes, data: bytes) -> bytes:
        if len(key_bytes) != 32 or not data or len(data) % 16:
            raise ValueError("Unreal PAK AES-256-ECB requires a 32-byte key and 16-byte-aligned data.")
        return AES.new(key_bytes, AES.MODE_ECB).decrypt(data)
    uepak.aes_decrypt = aes_decrypt
    print("[Mugiwara4iOS] Generic Linux AES compatibility enabled for NXNative PAK metadata inspection.", flush=True)

def shader_source_audit(facts: dict, flags: dict, reasons: dict) -> dict:
    """Persist NXNative profile_guess evidence; do not assume KTGL uses Unreal PAKs."""
    return {"graphics_api": str(facts["graphics"][0]), "flags": dict(flags), "reasons": dict(reasons)}

def run_preparation(args) -> dict:
    nx = args.nx2apple_root.resolve()
    packages = args.package_dir.resolve()
    keys = args.keys.resolve()
    work = args.work_dir.resolve()
    require(packages.is_dir(), f"Package directory missing: {packages}")
    require(keys.is_file(), "prod.keys was not downloaded to the Colab runtime.")
    pin_file = nx / ".upstream-ref"
    require(pin_file.is_file(), "NX2Apple .upstream-ref is missing.")
    pin = pin_file.read_text(encoding="utf-8").strip()
    require(pin == ENGINE_PIN, f"Wrong NXNative pin {pin}; expected {ENGINE_PIN}.")
    source_manifest_path = Path(getattr(args, "source_manifest", packages.parent / "source-manifest.json")).resolve()
    require(source_manifest_path.is_file(), f"mugi source manifest is missing: {source_manifest_path}")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    require(source_manifest.get("package_count") == 46
            and source_manifest.get("update_nsp_count") == 1
            and source_manifest.get("dlc_nsp_count") == 44
            and source_manifest.get("base_type") == "NSP",
            "Drive/mugi must provide exactly 1 base NSP + 1 update NSP + 44 DLC NSPs.")
    package_files = sorted(p for p in packages.iterdir() if p.is_file()
                           and p.suffix.lower() in (".nsp", ".xci"))
    require(len(package_files) == 46, f"Expected 46 package files in mugi (1 base + 1 update + 44 DLC); found {len(package_files)}.")
    require(all(path.suffix.lower() == ".nsp" for path in package_files),
            "This Mugiwara4iOS source set must contain 46 NSPs; no XCI is expected for this title's supplied links/DLCs.")
    source_packages = source_manifest.get("packages") or []
    require(len(source_packages) == 46, "mugi source manifest does not enumerate all 46 package files.")
    source_by_local = {item.get("local_name"): item for item in source_packages}
    require(set(source_by_local) == {path.name for path in package_files},
            "The local package directory differs from the 46-file source inventory recorded from Drive/mugi.")
    for path in package_files:
        with path.open("rb") as stream:
            header = stream.read(0x104)
        require(header[:4] == b"PFS0",
                f"{path.name}: every base/update/DLC input must be a valid NSP (PFS0 header).")
        expected = source_by_local[path.name]
        require(path.stat().st_size == int(expected.get("size", -1))
                and sha256_file(path) == expected.get("sha256"),
                f"{path.name}: local size/SHA-256 differs from the Drive/mugi source manifest.")
    base_items = [item for item in source_packages if item.get("role") == "base"]
    update_items = [item for item in source_packages if item.get("role") == "update"]
    dlc_items = [item for item in source_packages if item.get("role") == "dlc"]
    require(len(base_items) == 1 and len(update_items) == 1 and len(dlc_items) == 44,
            "Source inventory roles must be exactly 1 base + 1 update + 44 DLCs.")
    required_free = sum(path.stat().st_size for path in package_files) * 2 + 20 * 1024**3
    free_bytes = shutil.disk_usage(work.parent).free
    require(free_bytes >= required_free,
            f"Insufficient Colab disk space for 46 NSPs, the merged RomFS and 44 extracted DLC AOC images: {free_bytes / 2**30:.1f} GiB free; estimate {required_free / 2**30:.1f} GiB (twice all source bytes plus 20 GiB headroom).")
    print(f"[Mugiwara4iOS] Colab disk preflight for 46 NSPs + 44 AOC outputs: {free_bytes / 2**30:.1f} GiB free; estimate {required_free / 2**30:.1f} GiB.", flush=True)
    work.mkdir(parents=True, exist_ok=True)
    install_linux_dependencies(work.parent)
    module = load_builder(nx / "engine")
    install_linux_aes_compat()

    # Verify the Nintendo content metadata before the expensive extraction/rewrite.
    # File names do not classify DLC: NXNative uses each NSP's actual AddOnContent title ID.
    probe_env = module.tool_env()
    module.configure_dotnet(probe_env)
    with module.package_reader(nx / "engine", keys, probe_env) as reader:
        app, family = module.scan_nsps(packages, reader.contents, int(TITLE_ID, 16))
        reader.check_keys(family)
    require(app == int(TITLE_ID, 16), f"Content metadata belongs to {app:016X}, not {TITLE_ID}.")
    require(family.get("base") is not None and family["base"].name == base_items[0]["local_name"],
            "NXNative content metadata did not identify the supplied base NSP for the requested Title ID.")
    updates = family.get("updates", [])
    require(len(updates) == 1 and updates[0][1].name == update_items[0]["local_name"],
            f"NXNative content metadata must identify exactly the supplied update NSP; found {[x[1].name for x in updates]}.")
    dlc_family = family.get("dlc", [])
    dlc_paths = {item[2].name for item in dlc_family}
    expected_dlc_paths = {item["local_name"] for item in dlc_items}
    dlc_title_ids = {int(item[0]) for item in dlc_family}
    require(len(dlc_family) == 44 and len(dlc_title_ids) == 44
            and dlc_paths == expected_dlc_paths,
            "NXNative did not resolve the 44 source NSPs as 44 distinct AddOnContent entries for this title. "
            f"Detected {len(dlc_family)} entries/{len(dlc_title_ids)} unique title IDs and {len(dlc_paths)} source files.")
    print("[Mugiwara4iOS] Nintendo content-meta audit passed: 1 base + 1 update + 44 distinct DLC title IDs.", flush=True)
    work.mkdir(parents=True, exist_ok=True)
    for key in ("DM_GAMES_DIR", "DM_GAMES_FIRST"):
        os.environ.pop(key, None)
    os.environ["DM_GAME"] = TITLE_ID

    def defer_prereqs(*a, **k):
        print("[Mugiwara4iOS] Linux survey/rewrite stage: Xcode and Apple Metal checks deferred to xcode-27.", flush=True)
    def defer_metal(*a, **k):
        print("[Mugiwara4iOS] Apple Metal compilation deferred to macOS xcode-27.", flush=True)
    def defer_glslc_capture(*a, **k):
        print("[Mugiwara4iOS] Runtime GLSLC capture requires native macOS; deferred to xcode-27 ARM64.", flush=True)
        raise PreparedBoundary("glslc_capture")
    def defer_ue_decode(*a, **k):
        print("[Mugiwara4iOS] Unreal/Oodle shader archive decode is data-dependent and deferred to xcode-27 ARM64.", flush=True)
        raise PreparedBoundary("ue_decode")
    def defer_shader_split(*a, **k):
        print("[Mugiwara4iOS] NVN shader split and generated tables are deferred to xcode-27 ARM64.", flush=True)
        raise PreparedBoundary("shader_split")
    module.check_prereqs = defer_prereqs
    module.check_metal = defer_metal
    module.capture_glslc = defer_glslc_capture
    module.decode_ue_shaders = defer_ue_decode
    module.split_shaders = defer_shader_split

    argv = [str(packages), "-k", str(keys), "--title-id", TITLE_ID,
            "--work-dir", str(work), "--keep-extracted", "--progress", "lines",
            "--gpu", "none", "--no-heap-check"]
    parsed = module.parse_args(argv)
    boundary = None
    try:
        module.main(parsed)
        fail("NXNative finished without reaching the expected deferred shader boundary.")
    except PreparedBoundary as exc:
        boundary = exc.stage
    finally:
        try:
            module.PROG.close(ok=True)
        except Exception:
            pass
    require(boundary in ("glslc_capture", "ue_decode", "shader_split"), "NXNative stopped at an unexpected macOS-only preparation boundary.")

    patched_mains = sorted(work.glob("patched_*/main.patched.bin"))
    require(len(patched_mains) == 1, f"Expected one rewritten main; found {len(patched_mains)}.")
    package_version = patched_mains[0].parent.name.removeprefix("patched_")
    require(package_version != "v0", "The supplied update package was not recognized for One Piece: Pirate Warriors 4; refusing to prepare a base-only build.")
    version_dir = work / "extract" / package_version
    exefs = version_dir / "ExeFS"
    main = exefs / "main"
    patched = work / f"patched_{package_version}"
    romfs = version_dir / "RomFS.img"
    romfs_id = version_dir / "RomFS.img.id"
    for path, label in ((main, "extracted ExeFS/main"), (exefs / "main.npdm", "main.npdm"),
                        (patched / "main.patched.bin", "rewritten main"),
                        (patched / "main.fixups.tsv", "main fixups"),
                        (patched / "main.cuts.tsv", "main cut audit"),
                        (patched / "main.obs.tsv", "main observation audit"),
                        (romfs, "external RomFS.img"), (romfs_id, "RomFS identity sidecar")):
        require(path.is_file(), f"NXNative did not produce {label}: {path}")

    profile_root = work / "profile"
    profile_dir = profile_root / TITLE_ID
    require((profile_dir / "game.tsv").is_file(),
            f"NXNative did not generate the provisional One Piece: Pirate Warriors 4 profile: {profile_dir / 'game.tsv'}")
    os.environ["DM_GAMES_DIR"] = str(profile_root)
    os.environ["DM_GAMES_FIRST"] = "1"
    game_profiles = __import__("game")
    profile = game_profiles.load(TITLE_ID)
    require(profile.dir.resolve() == profile_dir.resolve(),
            f"Profile lookup selected an unexpected folder: {profile.dir}")
    profile_text = (profile_dir / "game.tsv").read_text(encoding="utf-8")
    profile_type = "provisional" if "Provisional game profile" in profile_text else "registered"
    require(profile_type == "provisional",
            "One Piece: Pirate Warriors 4 profile was expected to be generated by the pinned NXNative survey; refusing a hidden/registered profile substitution.")
    survey_source = packages / f"{TITLE_ID}_survey" / "survey.md"
    require(survey_source.is_file(),
            f"NXNative did not write the One Piece: Pirate Warriors 4 survey report: {survey_source}")
    survey_copy = work / "survey" / "survey.md"
    survey_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(survey_source, survey_copy)

    build_id = module.build_id(main)
    main_sha = sha256_file(main)
    modules = profile.modules_in(exefs)
    require("main" in modules, "Generated profile does not include the game's main module.")
    for name in modules:
        require((patched / f"{name}.patched.bin").is_file(),
                f"ARM64 rewritten module is missing: {name}.patched.bin")
        require((patched / f"{name}.fixups.tsv").is_file(),
                f"Rewriter fixup audit is missing for module {name}.")
    cuts = [x for x in (patched / "main.cuts.tsv").read_text(errors="replace").splitlines()
            if x.strip() and not x.lstrip().startswith("#")]
    observations = [x for x in (patched / "main.obs.tsv").read_text(errors="replace").splitlines()
                    if x.strip() and not x.lstrip().startswith("#")]
    fixups = (patched / "main.fixups.tsv").read_text(encoding="utf-8")
    module_artifacts = []
    for name in modules:
        patched_module = patched / f"{name}.patched.bin"
        module_fixups = patched / f"{name}.fixups.tsv"
        module_artifacts.append({
            "name": name,
            "patched_sha256": sha256_file(patched_module),
            "fixups_sha256": sha256_file(module_fixups),
        })
    rewrite_audit = {
        "main_build_id": build_id,
        "main_sha256": main_sha,
        "main_cut_rows": len(cuts),
        "main_observation_rows": len(observations),
        "fixups_sha256": hashlib.sha256(fixups.encode("utf-8")).hexdigest(),
        "modules": modules,
        "module_artifacts": module_artifacts,
    }
    facts = module.pg.build_sources(exefs, module.rfs.source(version_dir), modules)
    aoc_dir = work / "aoc"
    aoc_images = sorted(path for path in aoc_dir.glob("*.img") if path.is_file()) if aoc_dir.is_dir() else []
    expected_aoc_names = {f"{int(tid) - app - 0x1000}.img" for tid, _, _ in dlc_family}
    require(len(aoc_images) == 44 and {path.name for path in aoc_images} == expected_aoc_names,
            "NXNative did not extract all 44 DLCs into the expected AOC image set. "
            f"Found {[path.name for path in aoc_images]}; expected {sorted(expected_aoc_names)}.")
    require(all(path.stat().st_size > 0 for path in aoc_images), "At least one extracted DLC AOC image is empty.")
    aoc_records = [{"name": path.name, "size": path.stat().st_size, "sha256": sha256_file(path)}
                   for path in aoc_images]
    print("[Mugiwara4iOS] NXNative extracted and verified 44 external DLC AOC images.", flush=True)

    graphics = facts["graphics"][0]
    require(graphics == "nvn",
            f"One Piece: Pirate Warriors 4 was expected to use NVN; NXNative detected {graphics}: {facts['graphics'][1]}")
    shader_flags = {key: bool(facts.get(key, (False, ""))[0])
                    for key in ("ue_decode", "oodle_packs", "ue_legacy",
                                "glslc_capture", "vk_capture", "gl_capture")}
    shader_reasons = {key: str(facts[key][1]) for key in shader_flags if key in facts}
    audit = shader_source_audit(facts, shader_flags, shader_reasons)
    jit_required = bool(module.uses_jit(exefs))
    print("[Mugiwara4iOS] Shader source flags/reasons recorded from actual ExeFS/RomFS survey; no KTGL container is presumed.")
    print(f"[Mugiwara4iOS] nn::jit import detected: {jit_required}; if needed, NXNative will capture its AOT image on the Mac host for iOS (no runtime JIT).", flush=True)

    chain = module.chain_of(nx / "engine")
    require(bool(chain), "NXNative shader-chain version is missing after Linux preparation.")
    romfs_size = romfs.stat().st_size
    romfs_sha = sha256_file(romfs)
    try:
        identity = json.loads(romfs_id.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"Invalid RomFS identity sidecar: {exc}")
    require(identity.get("title") == TITLE_ID.lower(),
            "RomFS identity sidecar Title ID does not match One Piece: Pirate Warriors 4.")
    require(identity.get("version") == package_version,
            "RomFS identity sidecar package version differs from the selected update.")
    require(identity.get("bytes") == romfs_size and identity.get("sha256") == romfs_sha,
            "RomFS identity sidecar does not match the extracted RomFS bytes.")

    result = {
        "format": 3, "project": PROJECT, "title_id": TITLE_ID,
        "package_version": package_version, "nx2apple_tag": NX2APPLE_TAG,
        "engine_pin": pin, "profile_type": profile_type,
        "profile_source": "NXNative-generated provisional profile from One Piece: Pirate Warriors 4 base/update content metadata and ExeFS/RomFS survey",
        "profile_relative_dir": f"profile/{TITLE_ID}",
        "modules": modules, "main_build_id": build_id, "main_sha256": main_sha,
        "input_package_count": 46, "input_nsp_count": 46, "input_xci_count": 0,
        "input_base_package_type": "NSP", "input_base_package_name": base_items[0]["local_name"],
        "input_update_nsp_count": 1, "input_dlc_nsp_count": 44,
        "input_packages": [{**item, "sha256": item["sha256"]} for item in source_packages],
        "aoc_relative_dir": "aoc", "aoc_count": len(aoc_images), "aoc_images": aoc_records,
        "rewrite_audit": rewrite_audit,
        "graphics_api": graphics, "graphics_reason": facts["graphics"][1],
        "jit_required": jit_required,
        "shader_source_flags": shader_flags, "shader_source_reasons": shader_reasons,
"shader_source_audit": audit, "shader_chain": chain,
        "romfs_relative_path": f"extract/{package_version}/RomFS.img",
        "romfs_id_relative_path": f"extract/{package_version}/RomFS.img.id",
        "romfs_size": romfs_size, "romfs_sha256": romfs_sha,
        "survey_relative_path": "survey/survey.md",
        "survey_size": survey_copy.stat().st_size,
        "survey_sha256": sha256_file(survey_copy),
        "input_package_count": len(package_files),
        "input_packages": [{"name": p.name, "type": "XCI" if p.suffix.lower() == ".xci" else "NSP",
                            "size": p.stat().st_size, "sha256": sha256_file(p)} for p in package_files],
        "prepared_stages": [
            "mugi_content_meta_scan_1_base_1_update_44_DLC", "NXNative_base_update_RomFS_and_44_AOC_extraction",
            "NXNative_survey_and_provisional_game_profile",
            "ARM64_NSO_rewrite_and_fixup_audit", "RomFS_and_AOC_externalization",
            "engine_shader_source_classification_from_profile_guess",
        ],
        "deferred_stages": [
            "conditional_game_owned_Oodle_decode_on_macOS_ARM64",
            "shader_split_and_shader_tables_on_macOS_ARM64",
            "iOS_Metal_compile_and_chain_stamp_validation",
            "DmGame_framework", "Shared_Shell", "ad_hoc_thin_IPA",
        ],
        "shader_boundary": boundary,
    }
    manifest = work / "mugiwara4ios-linux-prep.json"
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description="One Piece: Pirate Warriors 4 Linux survey, profile generation and ARM64 rewrite")
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    run_preparation(parser.parse_args())

if __name__ == "__main__":
    main()
