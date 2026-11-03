#!/usr/bin/env python3
"""Build bloodborne-recomp's strict AOT dispatcher as an iOS ARM64 archive.

This intentionally excludes jit_arm64.c. The upstream GOW3_AOT_ONLY patch also
removes the JIT entry from bbcpu_run and makes every instruction-interpretation
fallback terminate. The archive is a real iOS object library, not a game-ready
runtime: the PS4 host services and GPU still have to be linked by the app.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

p = argparse.ArgumentParser()
p.add_argument("--recomp", type=Path, required=True)
p.add_argument("--zydis-include", type=Path, required=True)
p.add_argument("--zycore-include", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()

root = a.recomp.resolve()
cpu = root / "src/cpu"
interp = (cpu / "interp.c").read_text()
if "GOW3_AOT_ONLY" not in interp:
    raise SystemExit("Missing upstream strict AOT patch in interp.c")
if "ARM64 AOT coverage gap: function not recompiled" not in interp:
    raise SystemExit("Strict fail-closed dispatcher marker is absent")

sdk = subprocess.check_output(
    ["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True
).strip()
clang = subprocess.check_output(
    ["xcrun", "--sdk", "iphoneos", "--find", "clang"], text=True
).strip()
a.out.mkdir(parents=True, exist_ok=True)

# The ARM64 JIT translation unit is deliberately not compiled. The upstream
# AOT patch removes its only dispatcher call; no MAP_JIT/W^X code path is linked.
names = [
    "cpu.c", "decode.c", "interp.c", "interp_vec.c", "interp_x87.c",
    "native.c", "recomp.c", "record.c",
]
sources = [cpu / name for name in names] + [cpu / "hostcall.S"]
for src in sources:
    if not src.is_file():
        raise SystemExit("Missing pinned CPU source: " + str(src))

flags = [
    "-target", "arm64-apple-ios17.4", "-isysroot", sdk,
    "-O2", "-std=gnu11", "-fPIC", "-fno-strict-aliasing",
    "-DGOW3_AOT_ONLY=1", "-DGOW3_ARM64=1",
    "-I" + str(root / "src"), "-I" + str(cpu),
    "-I" + str(a.zydis_include), "-I" + str(a.zycore_include),
]
objects = []
for index, src in enumerate(sources):
    obj = a.out / f"{index:02d}-{src.stem}.o"
    print(f"iOS strict CPU [{index + 1}/{len(sources)}]: {src.name}", flush=True)
    subprocess.run([clang, *flags, "-c", str(src), "-o", str(obj)], check=True)
    objects.append(str(obj))

archive = a.out / "libgow3-aot-cpu-ios.a"
subprocess.run(["/usr/bin/libtool", "-static", "-o", str(archive), *objects], check=True)
arch = subprocess.check_output(["xcrun", "lipo", "-archs", str(archive)], text=True).strip()
if arch != "arm64":
    raise SystemExit("CPU archive is not arm64-only: " + arch)
nm = subprocess.check_output(["/usr/bin/nm", "-gU", str(archive)], text=True)
for symbol in ("_bbcpu_call", "_bbcpu_run", "_bbcpu_recomp_load", "_bbcpu_add_guest_code"):
    if symbol not in nm:
        raise SystemExit("Strict CPU archive is missing required dispatcher symbol " + symbol)
if "bbcpu_jit_run" in nm or "jit_arm64" in nm:
    raise SystemExit("JIT dispatcher unexpectedly present in strict AOT archive")

manifest = {
    "architecture": arch,
    "target": "arm64-apple-ios17.4",
    "upstream": "bloodborne-native/bloodborne-recomp@4b23a301944642f1e4e9e921418d4519dc36c315",
    "policy_patch": "xPXavierx/gow3-macos-arm64@eb9af23a198c577f8548a63471770e7b3316a369:packaging/macos/aot/bloodborne-recomp-arm64.patch",
    "compiled_sources": [str(x.relative_to(root)) for x in sources],
    "jit_translation_unit_compiled": False,
    "jit_dispatcher_linked": False,
    "interpreter_fallback": "fatal on first uncovered guest instruction/function",
    "required_external_libraries": ["Zydis", "Zycore"],
    "archive_bytes": archive.stat().st_size,
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "ps4_host_services_integrated": False,
    "gnm_renderer_integrated": False,
    "game_start_ready": False,
}
(a.out / "ios-cpu-runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
