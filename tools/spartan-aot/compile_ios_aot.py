#!/usr/bin/env python3
"""Compile only statically generated game functions for iOS ARM64.

This deliberately mirrors gow3-macos-arm64's native/compile_game.py:
only generated recomp*.c files are compiled. The upstream CPU runtime,
JIT, interpreter, instruction decoder and fallback engine are NOT part
of the game archive. The AOT loader/runtime must be supplied separately.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

p = argparse.ArgumentParser()
p.add_argument("--generated", type=Path, required=True)
p.add_argument("--recomp", type=Path, required=True)
p.add_argument("--zydis-include", type=Path, required=True)
p.add_argument("--zycore-include", type=Path, required=True)
p.add_argument("--coverage", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()

sdk = subprocess.check_output(
    ["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True
).strip()
clang = subprocess.check_output(
    ["xcrun", "--sdk", "iphoneos", "--find", "clang"], text=True
).strip()

a.out.mkdir(parents=True, exist_ok=True)
sources = sorted(a.generated.glob("recomp*.c"))
if not sources:
    raise SystemExit("No generated recomp*.c: refusing an empty AOT archive")

# Match gow3-macos-arm64 compile_game.py exactly: every generated
# recomp*.c translation unit, including the legitimate generated recomp.c.
# Never add the upstream src/cpu/*.c runtime files to this game-code archive.
if any(src.parent.resolve() != a.generated.resolve() for src in sources):
    raise SystemExit("AOT source escaped the generated directory")
coverage = json.loads(a.coverage.read_text())
if not isinstance(coverage.get("distinct_gap_sites"), int):
    raise SystemExit("Coverage audit is missing distinct_gap_sites")

flags = [
    "-target", "arm64-apple-ios17.4",
    "-isysroot", sdk,
    "-O2", "-std=gnu11", "-fPIC",
    "-ffp-contract=off", "-fno-strict-aliasing",
    "-I" + str(a.recomp / "src"),
    "-I" + str(a.recomp / "src/recomp"),
    "-I" + str(a.zydis_include),
    "-I" + str(a.zycore_include),
]
objects = []
for i, src in enumerate(sources):
    obj = a.out / f"{i:04d}-{src.stem}.o"
    print(f"AOT compile [{i + 1}/{len(sources)}]: {src.name}", flush=True)
    subprocess.run([clang, *flags, "-c", str(src), "-o", str(obj)], check=True)
    objects.append(str(obj))

archive = a.out / "libgow3-recompiled-ios.a"
subprocess.run(["/usr/bin/libtool", "-static", "-o", str(archive), *objects], check=True)
arch = subprocess.check_output(["xcrun", "lipo", "-archs", str(archive)], text=True).strip()
if arch != "arm64":
    raise SystemExit("AOT archive is not arm64-only: " + arch)

# bbcpu_recomp_load() uses dlopen/dlsym(BB_RECOMP_INIT), so the static archive alone is not loadable.
dylib = a.out / "libgow3-recompiled-ios.dylib"
subprocess.run([clang, "-target", "arm64-apple-ios17.4", "-isysroot", sdk, "-dynamiclib",
                "-Wl,-install_name,@rpath/libgow3-recompiled-ios.dylib", *objects, "-o", str(dylib)], check=True)
dylib_arch = subprocess.check_output(["xcrun", "lipo", "-archs", str(dylib)], text=True).strip()
if dylib_arch != "arm64":
    raise SystemExit("AOT dynamic library is not arm64-only: " + dylib_arch)
exports = subprocess.check_output(["/usr/bin/nm", "-gU", str(dylib)], text=True)
if "_bb_recomp_init" not in exports:
    raise SystemExit("AOT dynamic library does not export bb_recomp_init for bbcpu_recomp_load")

manifest = {
    "architecture": arch,
    "target": "arm64-apple-ios17.4",
    "generated_c_files": len(sources),
    "compiled_sources": [src.name for src in sources],
    "archive_bytes": archive.stat().st_size,
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "dynamic_library": dylib.name,
    "dynamic_library_bytes": dylib.stat().st_size,
    "dynamic_library_sha256": hashlib.sha256(dylib.read_bytes()).hexdigest(),
    "dynamic_library_install_name": "@rpath/libgow3-recompiled-ios.dylib",
    "dynamic_library_exports_recomp_init": True,
    "execution_model": "generated ARM64 archive only; no executable PS4 runtime integration",
    "complete_recompilation": False,
    "runtime_integrated": False,
    "game_start_ready": False,
    "compiled_cpu_runtime": False,
    "compiled_jit": False,
    "compiled_interpreter": False,
    "compiled_decoder": False,
    "compiled_fallback": False,
    "source_policy": "gow3-macos-arm64 packaging/macos/native/compile_game.py",
    "decoder_headers_only": True,
    "decoder_include": str(a.zydis_include),
    "decoder_dependency_include": str(a.zycore_include),
    "static_gap_sites": coverage["distinct_gap_sites"],
    "static_gap_mnemonics": coverage.get("gap_mnemonics"),
    "runtime_policy": "the archive is not executable by the app until a matching strict dispatcher and PS4 runtime are integrated; any reached gap must terminate, never interpret",
}
(a.out / "aot-build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
