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

# Never silently broaden this list to src/cpu/*.c. That directory contains
# jit_arm64.c, interp.c, decode.c and the hybrid dispatch/fallback runtime.
forbidden = ("jit_arm64.c", "interp.c", "decode.c", "cpu.c", "recomp.c")
if any(src.name in forbidden for src in sources):
    raise SystemExit("Generated-source set unexpectedly contains CPU runtime code")

flags = [
    "-target", "arm64-apple-ios17.4",
    "-isysroot", sdk,
    "-O2", "-std=gnu11", "-fPIC",
    "-ffp-contract=off", "-fno-strict-aliasing",
    "-I" + str(a.recomp / "src"),
    "-I" + str(a.recomp / "src/recomp"),
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

manifest = {
    "architecture": arch,
    "target": "arm64-apple-ios17.4",
    "generated_c_files": len(sources),
    "compiled_sources": [src.name for src in sources],
    "archive_bytes": archive.stat().st_size,
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "execution_model": "static generated ARM64 AOT only",
    "compiled_cpu_runtime": False,
    "compiled_jit": False,
    "compiled_interpreter": False,
    "compiled_decoder": False,
    "compiled_fallback": False,
    "source_policy": "gow3-macos-arm64 packaging/macos/native/compile_game.py",
}
(a.out / "aot-build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
