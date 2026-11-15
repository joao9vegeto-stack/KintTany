#!/usr/bin/env python3
"""Linux/Colab extraction, provisional-profile generation and ARM64 rewrite for Kakarot."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import struct
import sys
from pathlib import Path

TITLE_ID = "010051C0134F8000"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
PROJECT = "KaKaRoTiOS"

class PreparedBoundary(Exception):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage

def fail(message: str) -> None:
    raise SystemExit("[KaKaRoTiOS] ERROR: " + message)

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
        print("[KaKaRoTiOS] Installing Linux dependencies: " + ", ".join(missing), flush=True)
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
    print("[KaKaRoTiOS] Python, Linux tools and .NET 10 validated.", flush=True)

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
    spec = importlib.util.spec_from_file_location("kakarot_nxnative_builder", script)
    require(spec is not None and spec.loader is not None, "Could not load pinned NXNative build_ipa_from_nsp.py.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def install_linux_aes_compat() -> None:
    """Keep Unreal PAK index inspection working if this package build uses AES-encrypted indices."""
    from Crypto.Cipher import AES
    key = bytes(range(32))
    plain = bytes.fromhex("00112233445566778899aabbccddeeff")
    cipher = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")
    require(AES.new(key, AES.MODE_ECB).decrypt(cipher) == plain,
            "PyCryptodome AES-256-ECB self-test failed.")
    import uepak
    def decrypt(key_bytes: bytes, data: bytes) -> bytes:
        if len(key_bytes) != 32 or not data or len(data) % 16:
            raise ValueError("Unreal PAK AES-256-ECB requires a 32-byte key and 16-byte-aligned data.")
        return AES.new(key_bytes, AES.MODE_ECB).decrypt(data)
    uepak.aes_decrypt = decrypt

def pak_audit(romfs_source) -> dict:
    """Record PAK versions/methods. Kakarot's known UE4.22-4.25 format is PAK v8 + Zlib."""
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
    needs_game_oodle = bool(methods & {"oodle", "lz5", "custom", "kraken", "mermaid"})
    return {
        "pak_count": len(records),
        "readable_pak_count": len(readable),
        "versions": sorted({x["version"] for x in readable}),
        "compression_methods": sorted(methods),
        "oodle_host_required": needs_game_oodle,
        "records": records,
    }

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
    package_files = sorted(p for p in packages.iterdir() if p.is_file()
                           and p.suffix.lower() in (".nsp", ".xci"))
    base_package = packages / ("base.nsp" if (packages / "base.nsp").is_file() else "base.xci")
    update_package = packages / ("update.nsp" if (packages / "update.nsp").is_file() else "update.xci")
    require(base_package.is_file() and update_package.is_file(),
            "The package input directory must contain the reconstructed base and update separately.")
    dlc_packages = [p for p in package_files if p.name.startswith("dlc_")]
    require(len(package_files) == 2 + len(dlc_packages),
            "Unexpected NSP/XCI in input directory; only base, update and staged DLC packages are allowed.")
    for path in package_files:
        with path.open("rb") as stream:
            header = stream.read(0x104)
        detected = "NSP" if header[:4] == b"PFS0" else "XCI" if header[0x100:0x104] == b"HEAD" else None
        expected = "XCI" if path.suffix.lower() == ".xci" else "NSP"
        require(detected == expected, f"Invalid or mismatched package header in {path.name}: expected {expected}, detected {detected}.")
    required_free = sum(path.stat().st_size for path in package_files) * 2 + 10 * 1024**3
    free_bytes = shutil.disk_usage(work.parent).free
    require(free_bytes >= required_free,
            f"Insufficient Colab disk space before extraction: {free_bytes / 2**30:.1f} GiB free; estimated requirement is {required_free / 2**30:.1f} GiB (twice base+update bytes plus 10 GiB).")
    print(f"[KaKaRoTiOS] Colab disk preflight: {free_bytes / 2**30:.1f} GiB free; {required_free / 2**30:.1f} GiB estimated requirement.", flush=True)
    required_free = sum(path.stat().st_size for path in package_files) * 2 + 10 * 1024**3
    free_bytes = shutil.disk_usage(work.parent).free
    require(free_bytes >= required_free,
            f"Insufficient Colab disk space before NXNative extraction: {free_bytes / 2**30:.1f} GiB free; estimated requirement is {required_free / 2**30:.1f} GiB (two package copies plus 10 GiB).")
    print(f"[KaKaRoTiOS] Extraction disk preflight: {free_bytes / 2**30:.1f} GiB free; estimated requirement {required_free / 2**30:.1f} GiB.", flush=True)
    work.mkdir(parents=True, exist_ok=True)
    install_linux_dependencies(work.parent)
    module = load_builder(nx / "engine")
    install_linux_aes_compat()
    for key in ("DM_GAMES_DIR", "DM_GAMES_FIRST"):
        os.environ.pop(key, None)
    os.environ["DM_GAME"] = TITLE_ID

    def defer_prereqs(*a, **k):
        print("[KaKaRoTiOS] Linux survey/rewrite stage: Xcode and Apple Metal checks deferred to xcode-27.", flush=True)
    def defer_metal(*a, **k):
        print("[KaKaRoTiOS] Apple Metal compilation deferred to macOS xcode-27.", flush=True)
    def defer_ue_decode(*a, **k):
        print("[KaKaRoTiOS] Reached game-owned Unreal Oodle archive decode boundary; deferred to macOS ARM64.", flush=True)
        raise PreparedBoundary("ue_decode")
    def defer_shader_split(*a, **k):
        print("[KaKaRoTiOS] Reached shader split boundary; shader extraction/decoding and tables are deferred to macOS ARM64.", flush=True)
        raise PreparedBoundary("shader_split")
    module.check_prereqs = defer_prereqs
    module.check_metal = defer_metal
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
    require(boundary in ("ue_decode", "shader_split"), "NXNative stopped at an unexpected preparation boundary.")

    patched_mains = sorted(work.glob("patched_*/main.patched.bin"))
    require(len(patched_mains) == 1, f"Expected one rewritten main; found {len(patched_mains)}.")
    package_version = patched_mains[0].parent.name.removeprefix("patched_")
    require(package_version != "v0", "The supplied update package was not recognized for Kakarot; refusing to prepare a base-only build.")
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
            f"NXNative did not generate the provisional Kakarot profile: {profile_dir / 'game.tsv'}")
    os.environ["DM_GAMES_DIR"] = str(profile_root)
    os.environ["DM_GAMES_FIRST"] = "1"
    game_profiles = __import__("game")
    profile = game_profiles.load(TITLE_ID)
    require(profile.dir.resolve() == profile_dir.resolve(),
            f"Profile lookup selected an unexpected folder: {profile.dir}")
    profile_text = (profile_dir / "game.tsv").read_text(encoding="utf-8")
    profile_type = "provisional" if "Provisional game profile" in profile_text else "registered"
    require(profile_type == "provisional",
            "Kakarot profile was expected to be generated by the pinned NXNative survey; refusing a hidden/registered profile substitution.")
    survey_source = packages / f"{TITLE_ID}_survey" / "survey.md"
    require(survey_source.is_file(),
            f"NXNative did not write the Kakarot survey report: {survey_source}")
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
    graphics = facts["graphics"][0]
    require(graphics == "nvn",
            f"Kakarot was expected to use NVN; NXNative detected {graphics}: {facts['graphics'][1]}")
    shader_flags = {key: bool(facts.get(key, (False, ""))[0])
                    for key in ("ue_decode", "oodle_packs", "ue_legacy",
                                "glslc_capture", "vk_capture", "gl_capture")}
    shader_reasons = {key: str(facts[key][1]) for key in shader_flags if key in facts}
    pak_info = pak_audit(module.rfs.source(version_dir))
    require(pak_info["readable_pak_count"] > 0,
            "No readable Unreal PAKs were found in the extracted Kakarot RomFS.")
    if 8 not in pak_info["versions"]:
        print(f"[KaKaRoTiOS] NOTE: expected Kakarot PAK v8; found PAK versions {pak_info['versions']}. This build is recorded for macOS inspection.", flush=True)

    chain = module.chain_of(nx / "engine")
    require(bool(chain), "NXNative shader-chain version is missing after Linux preparation.")
    # NXNative extracts DLC NSPs (when supplied) to work/aoc/<index>.img.
    # No DLC package means an empty AOC directory; never synthesize DLC data.
    aoc_dir = work / "aoc"
    aoc_dir.mkdir(parents=True, exist_ok=True)
    aoc_images = sorted(p for p in aoc_dir.glob("*.img") if p.is_file() and not p.is_symlink())
    aoc_records = [{"name": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)}
                   for p in aoc_images]
    require(all(item["size"] > 0 for item in aoc_records), "NXNative produced an empty AOC image.")
    romfs_size = romfs.stat().st_size
    romfs_sha = sha256_file(romfs)
    try:
        identity = json.loads(romfs_id.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"Invalid RomFS identity sidecar: {exc}")
    require(identity.get("title") == TITLE_ID.lower(),
            "RomFS identity sidecar Title ID does not match Kakarot.")
    require(identity.get("version") == package_version,
            "RomFS identity sidecar package version differs from the selected update.")
    require(identity.get("bytes") == romfs_size and identity.get("sha256") == romfs_sha,
            "RomFS identity sidecar does not match the extracted RomFS bytes.")

    result = {
        "format": 1, "project": PROJECT, "title_id": TITLE_ID,
        "package_version": package_version, "nx2apple_tag": NX2APPLE_TAG,
        "engine_pin": pin, "profile_type": profile_type,
        "profile_source": "NXNative-generated provisional profile from Kakarot base/update content metadata and ExeFS/RomFS survey",
        "profile_relative_dir": f"profile/{TITLE_ID}",
        "modules": modules, "main_build_id": build_id, "main_sha256": main_sha,
        "rewrite_audit": rewrite_audit,
        "graphics_api": graphics, "graphics_reason": facts["graphics"][1],
        "unreal_shader_sources": shader_flags, "shader_source_reasons": shader_reasons,
        "pak_audit": pak_info, "shader_chain": chain,
        "romfs_relative_path": f"extract/{package_version}/RomFS.img",
        "romfs_id_relative_path": f"extract/{package_version}/RomFS.img.id",
        "romfs_size": romfs_size, "romfs_sha256": romfs_sha,
        "aoc_relative_dir": "aoc",
        "aoc_count": len(aoc_records),
        "aoc_images": aoc_records,
        "survey_relative_path": "survey/survey.md",
        "survey_size": survey_copy.stat().st_size,
        "survey_sha256": sha256_file(survey_copy),
        "input_package_count": len(package_files),
        "input_packages": [{"name": p.name, "type": "XCI" if p.suffix.lower() == ".xci" else "NSP",
                            "size": p.stat().st_size, "sha256": sha256_file(p)} for p in package_files],
        "prepared_stages": [
            "base_update_content_meta_scan", "base_update_NSP_XCI_extraction",
            "NXNative_survey_and_provisional_game_profile",
            "ARM64_NS0_rewrite_and_fixup_audit", "RomFS_externalization",
            "NVN_and_Unreal_PAK_shader_source_classification",
        ],
        "deferred_stages": [
            "conditional_game_owned_Oodle_decode_on_macOS_ARM64",
            "shader_split_and_shader_tables_on_macOS_ARM64",
            "iOS_Metal_compile_and_chain_stamp_validation",
            "DmGame_framework", "Shared_Shell", "ad_hoc_thin_IPA",
        ],
        "shader_boundary": boundary,
    }
    manifest = work / "kakarot-linux-prep.json"
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description="Kakarot Linux survey, profile generation and ARM64 rewrite")
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    run_preparation(parser.parse_args())

if __name__ == "__main__":
    main()
