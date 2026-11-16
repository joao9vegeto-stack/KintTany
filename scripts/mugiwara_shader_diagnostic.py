#!/usr/bin/env python3
"""Bounded A/B benchmark of Mugiwara pixel shaders with NXNative's uniform-tests rewrite."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

TITLE_ID = "01008FE00E2F6000"
SAMPLE_SECONDS = 150
PS_COUNT, VS_COUNT, CS_COUNT = 20, 2, 2
MARKER = "# MUGIWARA_DIAGNOSTIC_UNIFORM_TESTS"


def fail(message: str) -> None:
    raise SystemExit("[Mugiwara4iOS shader diagnostic] ERROR: " + message)


def select_even(items: list[tuple[str, str]], count: int) -> list[tuple[str, str]]:
    if not items:
        return []
    if len(items) <= count:
        return items
    indices = sorted({round(i * (len(items) - 1) / (count - 1)) for i in range(count)}) if count > 1 else [len(items) // 2]
    return [items[i] for i in indices]


def shader_sample(shader_map: Path) -> tuple[list[str], dict]:
    stages: dict[str, dict[str, str]] = collections.defaultdict(dict)
    with shader_map.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip() or line.startswith("#") or line.startswith("package\t"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 5:
                continue
            stage, key, source = fields[2], fields[3], fields[4]
            if re.fullmatch(r"[0-9a-f]{16}", key):
                stages[stage].setdefault(key, source)
    chosen = (
        select_even(sorted(stages.get("ps", {}).items()), PS_COUNT)
        + select_even(sorted(stages.get("vs", {}).items()), VS_COUNT)
        + select_even(sorted(stages.get("cs", {}).items()), CS_COUNT)
    )
    if len(chosen) < 8:
        fail(f"Shader map yielded too few sample keys: {len(chosen)}.")
    counts = {stage: len(values) for stage, values in stages.items()}
    return [key for key, _ in chosen], {
        "map_stage_counts": counts,
        "sample": [{"key": key, "source": source} for key, source in chosen],
        "sample_stage_counts": {
            stage: sum(1 for key, _ in chosen if key in stages.get(stage, {}))
            for stage in ("ps", "vs", "cs")
        },
    }


def diagnostic_build_source(original: str, uniform_fix: bool) -> str:
    src = original.replace(
        "dmsh_mtlcache, dmsh_pch,",
        "dmsh_mtlcache_diag as dmsh_mtlcache, dmsh_pch,",
        1,
    )
    if src == original:
        fail("Could not redirect dmsh_build to the instrumented Metal cache module.")

    import_anchor = "import dmsh_geometry,"
    if original.count(import_anchor) != 1:
        fail("Pinned dmsh_build.py import anchor changed; refusing diagnostic patch.")
    src = src.replace(import_anchor, "import mugiwara_uniform_rewrite_diag, dmsh_geometry,", 1)

    helper = "_MUGIWARA_UNIFORM_FIX = " + ("True" if uniform_fix else "False") + "\n"
    precise_anchor = "    src = precise(src)   # min / max / clamp with Maxwell's NaN results (see precise)\n"
    guard_call = (
        precise_anchor
        + "    if _MUGIWARA_UNIFORM_FIX:\n"
        + "        try: src = mugiwara_uniform_rewrite_diag.select_guards(src)\n"
        + "        except ValueError as e: return 'uniform guard rewrite failed', str(e)[:160], None\n"
    )
    if precise_anchor not in src:
        fail("Pinned dmsh_build precise() anchor changed; refusing diagnostic patch.")
    src = src.replace(precise_anchor, guard_call, 1)
    marker = "\ndef finish(key, w, j, c1):\n"
    if marker not in src:
        fail("Pinned dmsh_build finish() anchor changed; refusing diagnostic patch.")
    src = src.replace(marker, "\n" + helper + marker, 1)

    old_call = "    if j['stage'] == 'ps': src = frag_z_snap(src)[0]   # gl_FragCoord.z against a depth of its own surface (see frag_z_snap)\n"
    new_call = (
        old_call
        + "    _ut_probe = src\n"
        + "    if not _MUGIWARA_UNIFORM_FIX:\n"
        + "        try: _ut_probe = mugiwara_uniform_rewrite_diag.select_guards(src)\n"
        + "        except ValueError: pass\n"
        + "    _ut_words, _ut_sites = mugiwara_uniform_rewrite_diag.uniform_stats(_ut_probe)\n"
        + "    _ut_mode = 'on' if _MUGIWARA_UNIFORM_FIX else 'off'\n"
        + "    print('[MUGIWARA_UNIFORM_DIAG] key=%s stage=%s repeated_words=%d equality_tests=%d select_guards=%s uniform_pipeline=%s' % (key, j.get('stage', '?'), _ut_words, _ut_sites, _ut_mode, _ut_mode), flush=True)\n"
        + "    if _MUGIWARA_UNIFORM_FIX:\n"
        + "        try: src = mugiwara_uniform_rewrite_diag.uniform_tests(src)\n"
        + "        except ValueError as e: return 'uniform tests rewrite failed', str(e)[:160], None\n"
    )
    if old_call not in src:
        fail("Pinned dmsh_build shader rewrite anchor changed; refusing diagnostic patch.")
    src = src.replace(old_call, new_call, 1)

    src = src.replace("def finish(key, w, j, c1):", "def _mugiwara_finish_impl(key, w, j, c1):", 1)
    end_marker = "\nkeys = build_keys(want, loc, PAIRS)"
    wrapper = r'''
def finish(key, w, j, c1):
    started = time.perf_counter()
    try:
        return _mugiwara_finish_impl(key, w, j, c1)
    finally:
        print(f'[MUGIWARA_FINISH_TIME] key={key} stage={j.get("stage", "?")} wall={time.perf_counter()-started:.3f}s', flush=True)

'''
    if end_marker not in src:
        fail("Pinned dmsh_build orchestration anchor changed; refusing diagnostic patch.")
    src = src.replace(end_marker, "\n" + wrapper + end_marker, 1)
    return src


def diagnostic_mtlcache_source(original: str) -> str:
    instrumentation = r'''

# Mugiwara-only timing shim: reports cache hit versus actual Metal front-end+metallib wall time.
_mugi_original_compile = Cache.compile
def _mugi_timed_compile(self, target, msl, lib):
    before_compiled = self.stats.get((target, 'compiled'), 0)
    before_reused = self.stats.get((target, 'reused'), 0)
    size = os.path.getsize(msl) if os.path.isfile(msl) else 0
    started = time.perf_counter()
    try:
        return _mugi_original_compile(self, target, msl, lib)
    finally:
        compiled = self.stats.get((target, 'compiled'), 0) - before_compiled
        reused = self.stats.get((target, 'reused'), 0) - before_reused
        print(f'[MUGIWARA_METAL_TIME] target={target} mode={"compile" if compiled else "cache"} msl_bytes={size} wall={time.perf_counter()-started:.3f}s', flush=True)
Cache.compile = _mugi_timed_compile

_mugi_original_compile_split = Cache.compile_split
def _mugi_timed_compile_split(self, target, msl, libs, split):
    before_compiled = self.stats.get((target, 'compiled'), 0)
    before_reused = self.stats.get((target, 'reused'), 0)
    size = os.path.getsize(msl) if os.path.isfile(msl) else 0
    started = time.perf_counter()
    try:
        return _mugi_original_compile_split(self, target, msl, libs, split)
    finally:
        compiled = self.stats.get((target, 'compiled'), 0) - before_compiled
        reused = self.stats.get((target, 'reused'), 0) - before_reused
        print(f'[MUGIWARA_METAL_SPLIT_TIME] target={target} mode={"compile" if compiled else "cache"} msl_bytes={size} libs={len(libs)} wall={time.perf_counter()-started:.3f}s', flush=True)
Cache.compile_split = _mugi_timed_compile_split
'''
    if "class Cache:" not in original or "def compile_split(" not in original:
        fail("Pinned dmsh_mtlcache.py no longer exposes the expected Cache implementation.")
    return original + instrumentation


def write_diagnostic_sources(tool_dir: Path, uniform_fix: bool) -> list[Path]:
    build = (tool_dir / "dmsh_build.py").read_text(encoding="utf-8")
    wrapper = (tool_dir / "own_compilers.py").read_text(encoding="utf-8")
    mtlcache = (tool_dir / "dmsh_mtlcache.py").read_text(encoding="utf-8")
    build_diag = tool_dir / "dmsh_build_mugiwara_diag.py"
    wrapper_diag = tool_dir / "own_compilers_mugiwara_diag.py"
    mtlcache_diag = tool_dir / "dmsh_mtlcache_diag.py"
    rewrite_diag = tool_dir / "mugiwara_uniform_rewrite_diag.py"
    rewrite_source = Path(__file__).with_name("mugiwara_uniform_rewrite.py").read_text(encoding="utf-8")
    rewrite_diag.write_text(rewrite_source, encoding="utf-8")
    build_diag.write_text(diagnostic_build_source(build, uniform_fix), encoding="utf-8")
    wrapper_anchor = "sys.argv = [os.path.join(HERE, 'dmsh_build.py'), *sys.argv[1:]]"
    wrapper_replacement = "sys.argv = [os.path.join(HERE, 'dmsh_build_mugiwara_diag.py'), *sys.argv[1:]]"
    if wrapper.count(wrapper_anchor) != 1:
        fail("Pinned own_compilers.py dispatch anchor changed; refusing diagnostic wrapper.")
    wrapper_diag.write_text(wrapper.replace(wrapper_anchor, wrapper_replacement, 1), encoding="utf-8")
    mtlcache_diag.write_text(diagnostic_mtlcache_source(mtlcache), encoding="utf-8")
    for path in (build_diag, wrapper_diag, mtlcache_diag, rewrite_diag):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    return [build_diag, wrapper_diag, mtlcache_diag, rewrite_diag]


def run_case(label: str, uniform_fix: bool, tool_dir: Path, engine: Path, package: Path,
             root: Path, keys: list[str], base_env: dict) -> dict:
    paths = write_diagnostic_sources(tool_dir, uniform_fix)
    case = root / label
    out = case / "cache"
    ios = case / "ios"
    work = case / "work"
    logs = root / f"{label}.log"
    for path in (out, ios, work, work / "tmp"):
        path.mkdir(parents=True, exist_ok=True)
    env = dict(base_env)
    env.update({
        "DM_ROOT": str(work),
        "WORK": str(work / "tmp"),
        "IOSOUT": str(ios),
        "DMSH_TARGETS": "ios",
        "DMSH_CAS": str(case / "cas.db"),
        "DMSH_PROGRESS": str(case / "progress.json"),
        "J": "8",
        "XLATE": str(engine / "dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate"),
    })
    env.pop("DMSH_PROCS", None)
    cmd = [sys.executable, str(paths[1]), str(package), str(out), *keys]
    started = time.perf_counter()
    timed_out = False
    returncode = None
    with logs.open("w", encoding="utf-8") as stream:
        stream.write(f"[MUGIWARA_DIAG] case={label} uniform_pipeline={'on' if uniform_fix else 'off'} J=8 DMSH_PROCS=unset keys={len(keys)}\n")
        stream.flush()
        process = subprocess.Popen(
            cmd, cwd=engine, env=env, stdout=stream, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=SAMPLE_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            stream.write(f"\n[MUGIWARA_DIAG] hard timeout after {SAMPLE_SECONDS}s; terminating process group\n")
            stream.flush()
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            returncode = 124
        stream.flush()
    text = logs.read_text(encoding="utf-8", errors="replace")
    return {
        "label": label,
        "uniform_pipeline": uniform_fix,
        "keys": len(keys),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "timed_out": timed_out,
        "returncode": returncode,
        "finish_lines": [line for line in text.splitlines() if line.startswith("[MUGIWARA_FINISH_TIME]")],
        "metal_lines": [line for line in text.splitlines() if line.startswith(("[MUGIWARA_METAL_TIME]", "[MUGIWARA_METAL_SPLIT_TIME]"))],
        "uniform_lines": [line for line in text.splitlines() if line.startswith("[MUGIWARA_UNIFORM_DIAG]")],
        "summary_lines": [line for line in text.splitlines() if line.startswith(("shaders ", "shader cache:", "readable-tile", "pulling libraries"))],
        "log": str(logs),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--shader-package", type=Path, required=True)
    parser.add_argument("--shader-map", type=Path, required=True)
    parser.add_argument("--profile-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    engine = args.engine_root.resolve()
    package = args.shader_package.resolve()
    shader_map = args.shader_map.resolve()
    profile_root = args.profile_root.resolve()
    root = args.work_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    tool_dir = engine / "dm/gfx/tools"
    keys, sample_info = shader_sample(shader_map)
    base_env = dict(os.environ)
    base_env.update({
        "DM_GAME": TITLE_ID,
        "DM_GAMES_DIR": str(profile_root),
        "DM_GAMES_FIRST": "1",
        "DM_ROOT": str(root),
        "USER": base_env.get("USER") or "runner",
        "IOS_PULL": "1",
    })
    report = {
        "title_id": TITLE_ID,
        "engine_pin": "81906931262fb25d774cce8bca2db8926439e5a2",
        "sample_seconds_per_case": SAMPLE_SECONDS,
        "scheduler": "pinned NXNative stock ThreadPoolExecutor; J=8; DMSH_PROCS unset",
        **sample_info,
    }
    try:
        report["baseline"] = run_case("baseline", False, tool_dir, engine, package, root, keys, base_env)
        report["uniform_pipeline"] = run_case("uniform_pipeline", True, tool_dir, engine, package, root, keys, base_env)
    finally:
        for name in ("dmsh_build_mugiwara_diag.py", "own_compilers_mugiwara_diag.py", "dmsh_mtlcache_diag.py", "mugiwara_uniform_rewrite_diag.py"):
            (tool_dir / name).unlink(missing_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[Mugiwara4iOS shader diagnostic] A/B report: {args.report}", flush=True)
    print(json.dumps({k: report[k] for k in ("map_stage_counts", "sample_stage_counts", "baseline", "uniform_pipeline")}, indent=2), flush=True)
    if report["baseline"]["returncode"] not in (0, 124):
        fail(f"Baseline diagnostic failed with exit code {report['baseline']['returncode']}; see {report['baseline']['log']}.")
    if report["uniform_pipeline"]["returncode"] not in (0, 124):
        fail(f"Uniform-tests diagnostic failed with exit code {report['uniform_pipeline']['returncode']}; see {report['uniform_pipeline']['log']}.")
    print("[Mugiwara4iOS shader diagnostic] Bounded A/B completed; no IPA or full shader map was built.", flush=True)


if __name__ == "__main__":
    main()
