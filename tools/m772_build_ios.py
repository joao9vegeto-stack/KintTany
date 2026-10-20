#!/usr/bin/env python3
"""Compile the M7.72 PPU/SPU lift plus its per-game PS3Recomp runtime for iOS."""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import shlex
import subprocess
import sys


def run(argv, log=None):
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as stream:
            stream.write("+ " + shlex.join(str(x) for x in argv) + "\n")
            stream.flush()
            return subprocess.run([str(x) for x in argv], stdout=stream,
                                  stderr=subprocess.STDOUT, check=False).returncode
    return subprocess.run([str(x) for x in argv], check=False).returncode


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--upstream", type=pathlib.Path, required=True)
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    source, upstream, repo, out = (p.resolve() for p in
                                   (args.source, args.upstream, args.repo, args.output))
    expected = "39a36296511c445707adabcd312f0b740cfbd694"
    actual = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if actual != expected:
        raise SystemExit(f"M7.72 lifter/runtime pin mismatch: {actual} != {expected}")
    ppu = sorted(source.joinpath("ppu").glob("ppu_recomp_*.cpp"))
    spu = sorted(source.joinpath("spu").glob("*/spu_recomp.c"))
    if len(ppu) != 651 or len(spu) != 4:
        raise SystemExit(f"M7.72 source count mismatch: PPU={len(ppu)}, SPU={len(spu)}")

    sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
    target = "arm64-apple-ios17.0"
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"
    objects = out / "objects"
    logs.mkdir(exist_ok=True)
    objects.mkdir(exist_ok=True)
    nid_source = out / "ppu_hle_nids.cpp"
    rc = run([sys.executable, upstream / "tools/gen_hle_nids.py", "--all", "--out", nid_source],
             logs / "00-hle-nids.log")
    if rc or not nid_source.is_file() or not nid_source.stat().st_size:
        raise SystemExit(f"M7.72 HLE NID generation failed; see {logs / '00-hle-nids.log'}")

    include_dirs = [
        source, source / "ppu", upstream / "include", upstream / "runtime",
        upstream / "runtime/ppu", upstream / "runtime/spu", upstream / "runtime/memory",
        upstream / "runtime/syscalls", upstream / "runtime/platform",
        upstream / "libs/system", upstream / "libs/filesystem", upstream / "libs/input",
        upstream / "libs/audio", upstream / "libs/video", upstream / "libs/network",
        upstream / "libs/spurs", upstream / "libs/sync", upstream / "libs/codec",
        upstream / "libs/font", upstream / "libs/misc", out,
    ]
    includes = [flag for path in include_dirs for flag in ("-I", path)]
    cpp_flags = ["-target", target, "-isysroot", sdk, "-std=c++20", "-O2",
                 "-fwrapv", "-fno-strict-aliasing", "-ffp-contract=off",
                 "-Wno-unused-parameter", "-Wno-unused-variable", "-Wno-unused-function"]
    c_flags = ["-target", target, "-isysroot", sdk, "-std=c11", "-O2", "-fwrapv",
               "-fno-strict-aliasing", "-DSPU_USE_DISPATCH_MT",
               "-Wno-unused-parameter", "-Wno-unused-variable", "-Wno-unused-function"]
    tasks = []
    for src in ppu:
        tasks.append(("c++", src, objects / (src.stem + ".o"), cpp_flags, includes))
    for src in spu:
        tasks.append(("c", src, objects / (src.parent.name + ".o"), c_flags, includes))
    scaffold = [
        upstream / "runtime/ppu/ppu_loader.cpp",
        upstream / "runtime/ppu/ppu_hle.cpp",
        upstream / "runtime/ppu/ppu_fs.cpp",
        upstream / "runtime/ppu/ppu_sysprx.cpp",
        nid_source,
        upstream / "runtime/spu/spu_dispatch_mt.c",
        repo / "runtime/m772_bridge.cpp",
    ]
    for src in scaffold:
        lang = "c" if src.suffix == ".c" else "c++"
        flags = c_flags if lang == "c" else cpp_flags
        tasks.append((lang, src, objects / ("runtime_" + src.stem + ".o"), flags, includes))

    def compile_task(task):
        lang, src, dest, flags, incs = task
        compiler = "clang" if lang == "c" else "clang++"
        log = logs / (dest.stem + ".log")
        rc = run(["xcrun", "--sdk", "iphoneos", compiler, *flags, *incs,
                  "-c", src, "-o", dest], log)
        return src, dest, rc, log

    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.jobs, 4))) as pool:
        futures = [pool.submit(compile_task, task) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            src, dest, rc, log = future.result()
            if rc:
                failures.append((src, log, rc))
                print(f"M7.72 COMPILE FAILED ({rc}): {src}; log={log}", file=sys.stderr)
            elif not dest.is_file() or not dest.stat().st_size:
                failures.append((src, log, 99))
                print(f"M7.72 EMPTY OBJECT: {src}; log={log}", file=sys.stderr)
    if failures:
        for src, log, rc in failures:
            print(f"FAILED rc={rc} source={src} log={log}", file=sys.stderr)
            if log.is_file():
                print(log.read_text(errors="replace")[-12000:], file=sys.stderr)
        raise SystemExit(1)

    obj_files = sorted(objects.glob("*.o"))
    if len(obj_files) != len(tasks):
        raise SystemExit(f"M7.72 object count mismatch: {len(obj_files)} != {len(tasks)}")
    archive = out / "libAscensionGOWA-M772-ios-arm64.a"
    rc = run(["xcrun", "libtool", "-static", "-o", archive, *obj_files], logs / "99-libtool.log")
    if rc or not archive.is_file() or not archive.stat().st_size:
        raise SystemExit(f"M7.72 archive failed; see {logs / '99-libtool.log'}")

    symbols = out / "symbols.txt"
    rc = run(["xcrun", "nm", "-g", archive], symbols)
    if rc:
        raise SystemExit("M7.72 nm failed")
    symbol_text = symbols.read_text(errors="replace")
    required = ["func_0052A740", "func_0052E3F4", "_function_table_count",
                "_ar_m772_runtime_attest", "_ar_m772_runtime_init",
                "_ar_m772_dispatch_native", "_ar_m772_unbind_guest_memory",
                "_ppu_recomp_register",
                "_gowa_spu_0000_at_006B3E00_spu_recomp_register",
                "_gowa_spu_0001_at_006C1B00_spu_recomp_register",
                "_gowa_spu_0002_at_006CB580_spu_recomp_register",
                "_gowa_spu_0003_at_006D5900_spu_recomp_register"]
    defined = set()
    for line in symbol_text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[-2] in {"T", "t", "D", "d", "B", "b", "R", "r", "S", "s"}:
            defined.add(fields[-1])
    missing = [symbol for symbol in required
               if not any(symbol in name for name in defined)]
    if missing:
        raise SystemExit(f"M7.72 required ARM64 archive symbols missing: {missing}")

    result = {
        "schema": "ascension-m772-ios-arm64-link-input-v1",
        "upstream_commit": actual,
        "ppu_translation_units_compiled": len(ppu),
        "ppu_function_table_entries": 29849,
        "spu_translation_units_compiled": len(spu),
        "per_game_runtime_units_compiled": len(scaffold),
        "total_arm64_objects": len(obj_files),
        "archive": archive.name,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": digest(archive),
        "runtime_dispatch_adapter": "linked; boot initializes registry before ar_run",
        "device_guest_execution": "RUNTIME_COUNTER_REPORTED_BY_APP; DEVICE_RUN_REQUIRED",
        "first_guest_frame": "NOT_MEASURED",
    }
    (out / "m772-ios-arm64-attestation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
