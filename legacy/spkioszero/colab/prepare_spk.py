#!/usr/bin/env python3
"""Colab/Linux preparation for Sparking! ZERO; UE/Oodle decode and shader split are macOS-only."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, sys
from pathlib import Path

TITLE_ID = "010035F022078000"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
EXPECTED_MAIN_BUILD_ID = "68edafd68c7bc1a1af50b82aac838018"
EXPECTED_MAIN_SHA256 = "a0f8f0644c92384ddb1baac1c21aecbeeace5bc99ad40895e216add61da78efe"

class PreparedBoundary(Exception): pass
def fail(message: str) -> None: raise SystemExit("[SpkIOSzero] ERROR: " + message)
def require(condition: bool, message: str) -> None:
    if not condition: fail(message)

def install_linux_dependencies(root: Path) -> None:
    require(sys.platform.startswith("linux"), "Colab preparation must run on Linux.")
    require(sys.version_info >= (3, 12), "Python 3.12 or newer is required by NXNative.")
    # Debian/Ubuntu package names are not always the same as executable names.
    command_packages = {
        "git": "git",
        "zstd": "zstd",
        "curl": "curl",
        "cmake": "cmake",
        "ninja": "ninja-build",
        "pkg-config": "pkg-config",
    }
    missing_commands = [command for command in command_packages if shutil.which(command) is None]
    packages = ("build-essential", "libssl-dev")
    def installed(name: str) -> bool:
        result = subprocess.run(["dpkg-query", "-W", "-f=${db:Status-Status}", name],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return result.returncode == 0 and result.stdout.strip() == "installed"
    missing_packages = [command_packages[name] for name in missing_commands]
    missing_packages += [name for name in packages if not installed(name)]
    # Avoid asking APT to install packages already present under another executable path.
    missing_packages = list(dict.fromkeys(name for name in missing_packages if not installed(name)))
    if missing_packages:
        print("[SpkIOSzero] Installing missing Linux packages:", ", ".join(missing_packages), flush=True)
        update = subprocess.run(["apt-get", "update", "-qq"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if update.returncode:
            fail("apt-get update failed (exit "
                 + str(update.returncode) + "): " + update.stdout[-3000:])
        install = subprocess.run(["apt-get", "install", "-y", "-qq", *missing_packages],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if install.returncode:
            fail("apt-get install failed (exit " + str(install.returncode)
                 + ") for " + ", ".join(missing_packages) + ": " + install.stdout[-4000:])
    still_missing = [name for name in command_packages if shutil.which(name) is None]
    if still_missing:
        fail("Linux dependencies are still unavailable after APT installation: "
             + ", ".join(still_missing))
    python_packages = (
        ("lz4.block", "lz4"), ("capstone", "capstone>=5,<6"),
        ("fontTools", "fonttools"), ("zbic", "zbic"),
        ("backports.zstd", "backports.zstd"), ("requests", "requests"),
        ("Crypto.Cipher", "pycryptodome"),
    )
    missing_pip = []
    for module_name, package_name in python_packages:
        try:
            if importlib.util.find_spec(module_name) is None: missing_pip.append(package_name)
        except (ImportError, ModuleNotFoundError, ValueError): missing_pip.append(package_name)
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
        result = subprocess.run([str(dotnet), "--list-runtimes"], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.returncode == 0: runtimes = result.stdout
    if not re.search(r"^Microsoft\.NETCore\.App\s+10\.", runtimes, re.M):
        dotnet_root.mkdir(parents=True, exist_ok=True)
        install_script = root / "dotnet-install.sh"
        subprocess.run(["curl", "-fsSL", "https://dot.net/v1/dotnet-install.sh", "-o", str(install_script)], check=True)
        subprocess.run(["bash", str(install_script), "--channel", "10.0", "--install-dir", str(dotnet_root)], check=True)
        env = os.environ.copy()
        env.update({"DOTNET_ROOT": str(dotnet_root), "DOTNET_ROOT_X64": str(dotnet_root),
                    "DOTNET_HOST_PATH": str(dotnet),
                    "PATH": str(dotnet_root) + os.pathsep + env.get("PATH", "")})
        runtimes = subprocess.run([str(dotnet), "--list-runtimes"], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True).stdout
    require(dotnet.is_file(), "The .NET 10 host was not installed.")
    require(bool(re.search(r"^Microsoft\.NETCore\.App\s+10\.", runtimes, re.M)),
            "The Microsoft.NETCore.App 10.x runtime is missing.")
    os.environ.update({"DOTNET_ROOT": str(dotnet_root), "DOTNET_ROOT_X64": str(dotnet_root),
                       "DOTNET_HOST_PATH": str(dotnet),
                       "PATH": str(dotnet_root) + os.pathsep + os.environ.get("PATH", "")})
    print("[SpkIOSzero] .NET 10, Python modules and Linux tools validated.", flush=True)

def load_builder(engine: Path):
    script = engine / "scripts" / "build_ipa_from_nsp.py"
    require(script.is_file(), f"NXNative builder not found: {script}")
    # Colab sessions are long-lived: never reuse NXNative modules from another checkout/ref.
    for module_name in (
        "game", "nacp", "profile_guess", "nso", "nso_syms", "nso_asm",
        "uepak", "uepak_extract", "nso_match", "sdk_patches", "pack_nup",
        "pack_dump", "nx_extract", "patch_nso",
    ):
        sys.modules.pop(module_name, None)
    importlib.invalidate_caches()
    for folder in (engine / "dm/tools", engine / "dm/games", engine / "dm/gfx/tools", engine / "scripts"):
        sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("spk_nxnative_builder", script)
    require(spec is not None and spec.loader is not None, "Could not load the pinned NXNative builder.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()

def install_linux_aes_compat() -> None:
    """Provide the upstream uepak reader with AES-256-ECB on Colab/Linux.

    NXNative's default implementation calls macOS CommonCrypto. Without this
    compatibility backend, encrypted PAK indexes are treated as keyless and
    Sparking! ZERO's inline IoStore shaders are misclassified as shader archives.
    """
    require(sys.platform.startswith("linux"), "Linux AES compatibility is only used in Colab preparation.")
    from Crypto.Cipher import AES
    key = bytes(range(32))
    plaintext = bytes.fromhex("00112233445566778899aabbccddeeff")
    ciphertext = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")
    require(AES.new(key, AES.MODE_ECB).decrypt(ciphertext) == plaintext,
            "PyCryptodome AES-256-ECB self-test failed.")
    import uepak
    def aes_decrypt(key_bytes: bytes, data: bytes) -> bytes:
        if len(key_bytes) != 32 or not data or len(data) % 16:
            raise ValueError("Unreal pak AES-256-ECB requires a 32-byte key and 16-byte-aligned data.")
        return AES.new(key_bytes, AES.MODE_ECB).decrypt(data)
    uepak.aes_decrypt = aes_decrypt
    print("[SpkIOSzero] Linux AES-256-ECB enabled for encrypted Unreal PAK index classification.", flush=True)

def run_preparation(args) -> dict:
    nx, nsp_dir, keys, work = (args.nx2apple_root.resolve(), args.nsp_dir.resolve(),
                                args.keys.resolve(), args.work_dir.resolve())
    require(nsp_dir.is_dir(), f"NSP input directory does not exist: {nsp_dir}")
    require(keys.is_file(), "prod.keys was not downloaded from the configured Drive folder.")
    pin_file = nx / ".upstream-ref"
    require(pin_file.is_file(), "NX2Apple engine pin file is missing.")
    pin = pin_file.read_text(encoding="utf-8").strip()
    require(pin == ENGINE_PIN, f"Wrong NXNative pin: {pin}; expected {ENGINE_PIN}.")
    work.mkdir(parents=True, exist_ok=True)
    install_linux_dependencies(work.parent)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import spk_engine
    # Use the registered NXNative profile, not a generated provisional shadow.
    for key in ("DM_GAMES_DIR", "DM_GAMES_FIRST"):
        os.environ.pop(key, None)
    os.environ["DM_GAME"] = TITLE_ID
    upstream_allocator = spk_engine.verify(nx / "engine")
    module = load_builder(nx / "engine")
    install_linux_aes_compat()
    import game as game_profiles
    registered_profile = game_profiles.load(TITLE_ID)
    expected_profile_dir = (nx / "engine" / "dm/games" / TITLE_ID).resolve()
    require(registered_profile.dir.resolve() == expected_profile_dir,
            f"NXNative selected a non-upstream profile: {registered_profile.dir}")
    require(not (expected_profile_dir / "patches.py").exists(),
            "The registered upstream Sparking! ZERO profile unexpectedly contains a custom patches.py.")
    require(registered_profile.builds().get("v327680", {}).get("main") == EXPECTED_MAIN_BUILD_ID,
            "The registered upstream game profile does not match the inspected main build.")
    package_files = module.files_with_suffix(nsp_dir, ".nsp", ".xci")
    nsp_files = [p for p in package_files if p.suffix.lower() == ".nsp"]
    xci_files = [p for p in package_files if p.suffix.lower() == ".xci"]
    expected_dlc_count = int(getattr(args, "expected_dlc_count", 10))
    expected_package_count = int(getattr(args, "expected_package_count", 12))
    require(expected_dlc_count == 10 and expected_package_count == 12,
            "SpkIOSzero input contract is 1 base package (.nsp or .xci) + 1 update.nsp + 10 DLC NSPs.")
    base_files = [p for p in package_files if p.name.lower().startswith("000_base.")]
    require(len(base_files) == 1 and base_files[0].suffix.lower() in (".nsp", ".xci"),
            f"Expected exactly one 000_base.nsp or 000_base.xci; found {[p.name for p in base_files]}.")
    base_file = base_files[0]
    extra_packages = [p for p in package_files if p != base_file]
    require(len(package_files) == 12 and len(extra_packages) == 11
            and all(p.suffix.lower() == ".nsp" for p in extra_packages),
            f"Expected 1 base package + 1 update NSP + 10 DLC NSPs; found {len(package_files)} package(s), {len(nsp_files)} NSP(s), {len(xci_files)} XCI(s).")
    require(len(xci_files) == (1 if base_file.suffix.lower() == ".xci" else 0),
            "An XCI is supported only as the single base package; update and DLC inputs must be NSP.")
    for path in package_files:
        require(module.is_package(path),
                f"Invalid Nintendo package header for {path.name}: expected PFS0 (NSP) or XCI HEAD at offset 0x100.")
    base_package_type = "XCI" if base_file.suffix.lower() == ".xci" else "NSP"

    original_rewrite = module.rewrite
    def rewrite_with_spk_guard(py, repo, exe_dir, out, env, logs, game, provisional=False):
        main = exe_dir / "main"
        require(main.is_file(), f"Extracted ExeFS/main is missing: {main}")
        build_id, digest = module.build_id(main), sha256_file(main)
        if build_id != EXPECTED_MAIN_BUILD_ID or digest != EXPECTED_MAIN_SHA256:
            fail("The upstream Sparking! ZERO profile and generic allocator detector apply only to the inspected main build. "
                 f"Received Build ID {build_id}, SHA-256 {digest}; expected "
                 f"{EXPECTED_MAIN_BUILD_ID} / {EXPECTED_MAIN_SHA256}.")
        require(game.dir.resolve() == registered_profile.dir.resolve(),
                f"NXNative rewrite received an unexpected game profile: {game.dir}")
        print(f"[SpkIOSzero] Exact registered main verified: Build ID {build_id}; SHA-256 {digest}.", flush=True)
        result = original_rewrite(py, repo, exe_dir, out, env, logs, game, provisional)
        for filename in ("main.patched.bin", "main.fixups.tsv", "main.cuts.tsv", "main.obs.tsv"):
            require((out / filename).is_file(), f"NXNative rewrite output missing: {out / filename}")
        cuts = [line for line in (out / "main.cuts.tsv").read_text(errors="replace").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
        obs = [line for line in (out / "main.obs.tsv").read_text(errors="replace").splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
        fixups = (out / "main.fixups.tsv").read_text(encoding="utf-8")

        allocator_cut_offsets = {
            int(row.split("\t", 1)[0], 0)
            for row in cuts if "FMallocBinned3" in row
        }
        allocator_obs_offsets = {
            int(row.split("\t", 1)[0], 0)
            for row in obs if "FMallocBinned3 constructor call (cut)" in row
        }
        expected_calls = set(spk_engine.ALLOCATOR_CALLS)
        require(allocator_cut_offsets == expected_calls,
                "NXNative did not cut both upstream FMallocBinned3 constructor calls: "
                f"expected {[hex(x) for x in sorted(expected_calls)]}, got {[hex(x) for x in sorted(allocator_cut_offsets)]}.")
        require(allocator_obs_offsets == expected_calls,
                "NXNative did not install an x0 allocator observation gate at both constructor call sites: "
                f"expected {[hex(x) for x in sorted(expected_calls)]}, got {[hex(x) for x in sorted(allocator_obs_offsets)]}.")
        require(f"# UE_MALLOC_VT\t{spk_engine.VTABLE:#x}" in fixups
                and f"# UE_MALLOC_SLOT\t{spk_engine.GETTER_SLOT:#x}" in fixups,
                "NXNative fixups do not identify Sparking! ZERO's vtable and getter slot 19.")
        print("[SpkIOSzero] Upstream allocator rewrite audit passed: 2 constructor cuts, 2 generic x0 gates, "
              "vtable 0x8703ab8, getter slot 19.", flush=True)
        return result

    module.rewrite = rewrite_with_spk_guard
    module.check_prereqs = lambda *a, **k: print("[SpkIOSzero] Linux prerequisite check passed; Xcode/Metal are deferred.")
    module.check_metal = lambda *a, **k: print("[SpkIOSzero] Apple Metal compilation is deferred to macOS.")
    def defer_unreal_decode(*a, **k):
        print("[SpkIOSzero] Reached Unreal shader decode boundary; Oodle decode and shader split are deferred to macOS.", flush=True)
        raise PreparedBoundary()
    def defer_shader_split(*a, **k):
        print("[SpkIOSzero] Reached shader split boundary; this project requires the Mac host's Oodle decoder.", flush=True)
        raise PreparedBoundary()
    module.decode_ue_shaders = defer_unreal_decode
    module.split_shaders = defer_shader_split

    argv = [str(nsp_dir), "-k", str(keys), "--title-id", TITLE_ID, "--work-dir", str(work),
            "--keep-extracted", "--progress", "lines", "--gpu", "none"]
    parsed = module.parse_args(argv)
    try:
        module.main(parsed)
        fail("NXNative completed without reaching the expected pre-shader boundary; refusing to package an unverified Linux shader result.")
    except PreparedBoundary:
        pass
    finally:
        try: module.PROG.close(ok=True)
        except Exception: pass

    patched_mains = sorted(work.glob("patched_*/main.patched.bin"))
    require(len(patched_mains) == 1, f"Expected one rewritten SPK main; found {len(patched_mains)}.")
    package_version = patched_mains[0].parent.name.removeprefix("patched_")
    version_dir = work / "extract" / package_version
    require(version_dir.is_dir(), f"Extracted package version directory missing: {version_dir}")
    exefs, main = version_dir / "ExeFS", version_dir / "ExeFS" / "main"
    require(main.is_file() and module.build_id(main) == EXPECTED_MAIN_BUILD_ID
            and sha256_file(main) == EXPECTED_MAIN_SHA256,
            "Final extracted main does not match the exact inspected Sparking! ZERO build.")
    patched = work / f"patched_{package_version}"
    profile_dir = nx / "engine" / "dm/games" / TITLE_ID
    for path, label in (
        (version_dir / "RomFS.img", "external RomFS image"),
        (version_dir / "RomFS.img.id", "RomFS identity sidecar"),
        (exefs / "main.npdm", "main.npdm"),
        (patched / "main.patched.bin", "rewritten main"),
        (patched / "main.fixups.tsv", "main fixups"),
        (patched / "main.cuts.tsv", "main cut audit"),
        (patched / "main.obs.tsv", "main observation audit"),
        (profile_dir / "game.tsv", "upstream registered game profile"),
    ): require(path.is_file(), f"NXNative did not provide {label}: {path}")
    require(not (profile_dir / "patches.py").exists(),
            "Unexpected local patch file shadows the pinned upstream Sparking! ZERO profile.")

    import game as game_profiles
    profile = game_profiles.load(TITLE_ID)
    require(profile.dir.resolve() == profile_dir.resolve(),
            f"NXNative selected a non-upstream game profile: {profile.dir}")
    require(profile.builds().get("v327680", {}).get("main") == EXPECTED_MAIN_BUILD_ID,
            "The selected registered profile does not match the exact 2.0.76 main Build ID.")
    modules = profile.modules_in(exefs)
    for name in modules:
        require((patched / f"{name}.patched.bin").is_file(), f"Rewritten module missing: {name}")
        require((patched / f"{name}.fixups.tsv").is_file(), f"Rewrite fixups missing: {name}")

    cuts = [line for line in (patched / "main.cuts.tsv").read_text(errors="replace").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    obs = [line for line in (patched / "main.obs.tsv").read_text(errors="replace").splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
    fixups = (patched / "main.fixups.tsv").read_text(encoding="utf-8")
    allocator_cut_offsets = {
        int(row.split("\t", 1)[0], 0) for row in cuts if "FMallocBinned3" in row
    }
    allocator_obs_offsets = {
        int(row.split("\t", 1)[0], 0)
        for row in obs if "FMallocBinned3 constructor call (cut)" in row
    }
    expected_calls = set(spk_engine.ALLOCATOR_CALLS)
    require(allocator_cut_offsets == expected_calls,
            "NXNative did not cut both upstream FMallocBinned3 constructors: "
            f"expected {[hex(x) for x in sorted(expected_calls)]}, got {[hex(x) for x in sorted(allocator_cut_offsets)]}.")
    require(allocator_obs_offsets == expected_calls,
            "NXNative did not gate both FMallocBinned3 constructors through x0: "
            f"expected {[hex(x) for x in sorted(expected_calls)]}, got {[hex(x) for x in sorted(allocator_obs_offsets)]}.")
    require(f"# UE_MALLOC_VT\t{spk_engine.VTABLE:#x}" in fixups
            and f"# UE_MALLOC_SLOT\t{spk_engine.GETTER_SLOT:#x}" in fixups,
            "NXNative fixups do not identify the Sparking! ZERO vtable and getter slot 19.")
    print("[SpkIOSzero] Upstream allocator audit passed: both constructor calls are cut and gated; "
          "vtable 0x8703ab8, getter slot 19.", flush=True)

    facts = module.pg.build_sources(exefs, module.rfs.source(version_dir), modules)
    graphics = facts["graphics"][0]
    require(graphics == "nvn", f"Sparking! ZERO expected NVN graphics; NXNative detected {graphics}: {facts['graphics'][1]}.")
    ue_flags = {key: bool(facts.get(key, (False, ""))[0]) for key in ("ue_decode", "oodle_packs", "ue_legacy")}
    expected_ue_flags = {"ue_decode": False, "oodle_packs": False, "ue_legacy": True}
    require(ue_flags == expected_ue_flags,
            "Sparking! ZERO 2.0.76 shaders must be classified as inline Unreal IoStore packages "
            "(ue_legacy=True, ue_decode=False, oodle_packs=False). "
            f"NXNative detected {ue_flags}; this indicates its encrypted PAK index was not opened correctly.")

    romfs = version_dir / "RomFS.img"
    aoc_dir = work / "aoc"
    aoc_images = sorted(p for p in aoc_dir.glob("*.img") if p.is_file()) if aoc_dir.is_dir() else []
    require(aoc_images, "No DLC AOC images were extracted from the 10 DLC NSPs under Drive/spk.")
    require(all(p.stat().st_size > 0 for p in aoc_images), "At least one extracted DLC AOC image is empty.")
    shader_chain = module.chain_of(nx / "engine")
    require(bool(shader_chain), "NXNative shader chain header is missing after Linux preparation.")
    result = {
        "format": 1, "project": "SpkIOSzero", "title_id": TITLE_ID,
        "package_version": package_version, "nx2apple_tag": NX2APPLE_TAG, "engine_pin": pin,
        "input_package_count": len(package_files),
        "input_nsp_count": len(nsp_files),
        "input_xci_count": len(xci_files),
        "input_base_package_type": base_package_type,
        "input_base_package_name": base_file.name,
        "input_base_nsp_count": int(base_package_type == "NSP"),
        "input_base_xci_count": int(base_package_type == "XCI"),
        "input_update_nsp_count": 1,
        "input_dlc_nsp_count": 10,
        "profile_type": "registered", "profile_source": "NXNative pinned built-in Sparking! ZERO profile",
        "modules": modules,
        "main_build_id": EXPECTED_MAIN_BUILD_ID, "main_sha256": EXPECTED_MAIN_SHA256,
        "allocator": {"detector": upstream_allocator["allocator"], "layout": upstream_allocator["layout"],
            "vtable": upstream_allocator["vtable"], "getter_slot": upstream_allocator["getter_slot"],
            "constructor_calls": upstream_allocator["constructor_calls"],
            "object_register": upstream_allocator["object_register"]},
        "graphics_api": graphics, "unreal_shader_sources": ue_flags, "shader_chain": shader_chain,
        "romfs_relative_path": f"extract/{package_version}/RomFS.img",
        "romfs_id_relative_path": f"extract/{package_version}/RomFS.img.id",
        "aoc_relative_dir": "aoc", "romfs_size": romfs.stat().st_size,
        "aoc_images": [{"name": p.name, "size": p.stat().st_size} for p in aoc_images],
        "prepared_stages": ["content_meta_scan", "base_update_DLC_extraction",
            "RomFS_and_AOC_creation", "upstream_generic_FMallocBinned3_two_call_AArch64_rewrite"],
        "deferred_stages": ["Unreal_Oodle_decode_on_macOS", "shader_split_on_macOS",
            "iOS_Metal_compile", "game_framework", "Shared_Shell", "ad_hoc_thin_IPA"],
    }
    (work / "spk-ios-zero-linux-prep.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return result

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nx2apple-root", type=Path, required=True)
    parser.add_argument("--nsp-dir", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    run_preparation(parser.parse_args())

if __name__ == "__main__": main()
