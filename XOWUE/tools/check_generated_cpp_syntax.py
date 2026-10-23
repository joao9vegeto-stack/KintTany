#!/usr/bin/env python3
"""Syntax-check every generated XOWUE C++ translation unit with Clang."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def main() -> int:
    script_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpp-dir", type=Path, default=script_root / "generated" / "ppc")
    parser.add_argument(
        "--xenonrecomp-root",
        type=Path,
        default=os.environ.get("XENONRECOMP_ROOT"),
        help="XenonRecomp checkout containing XenonUtils and thirdparty/simde",
    )
    parser.add_argument("--compiler", default=os.environ.get("CXX", "clang++-18"))
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()

    if args.xenonrecomp_root is None:
        parser.error("set XENONRECOMP_ROOT or pass --xenonrecomp-root")
    cpp_dir = args.cpp_dir.resolve()
    xenon_root = args.xenonrecomp_root.resolve()
    files = sorted(cpp_dir.glob("*.cpp"))
    if not files:
        parser.error(f"no generated .cpp files found in {cpp_dir}")
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")

    command_prefix = [
        args.compiler,
        "-std=gnu++23",
        "-fsyntax-only",
        f"-I{cpp_dir}",
        f"-I{xenon_root / 'XenonUtils'}",
        f"-I{xenon_root / 'thirdparty' / 'simde'}",
    ]
    started = time.monotonic()
    print(f"Checking {len(files)} C++ files with {min(args.jobs, 4)} workers", flush=True)

    def check(path: Path) -> tuple[str, int, str]:
        result = subprocess.run(
            command_prefix + [str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return path.name, result.returncode, result.stderr

    failures: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=min(args.jobs, 4)) as pool:
        pending = [pool.submit(check, path) for path in files]
        done = 0
        for future in as_completed(pending):
            name, returncode, stderr = future.result()
            done += 1
            if returncode:
                failures.append((name, stderr))
            if done % 50 == 0 or done == len(files):
                print(f"{done}/{len(files)} checked; failures={len(failures)}", flush=True)

    config_dir = script_root / "generated" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    summary_path = config_dir / "XOWUE-cpp-syntax-summary.txt"
    elapsed = time.monotonic() - started
    summary_path.write_text(
        "clang++ -std=gnu++23 -fsyntax-only\n"
        f"translation_units={len(files)}\n"
        f"failures={len(failures)}\n"
        f"elapsed_seconds={elapsed:.1f}\n",
        encoding="utf-8",
    )

    failure_path = config_dir / "XOWUE-cpp-syntax-failures.log"
    if failures:
        failure_path.write_text(
            "\n".join(f"[{name}]\n{stderr}" for name, stderr in failures),
            encoding="utf-8",
        )
        print(f"Failures written to {failure_path}", file=sys.stderr)
        return 1
    if failure_path.exists():
        failure_path.unlink()
    print(f"PASS: all {len(files)} translation units passed syntax checking.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
