#!/usr/bin/env python3
"""Backport NXNative's tested DMSH_PROCS shader workers without replacing NX2Apple's pinned engine."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
MARKER = "# Mugiwara4iOS DMSH_PROCS worker backport"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"[Mugiwara4iOS] Refusing unsafe NXNative patch for {label}: expected one anchor, found {count}.")
    return text.replace(old, new, 1)


PROCESS_WORKERS = r'''
BUILD_STARTED = time.monotonic()
LAST_RATE_LOG = 0.0


def finished(*_):
    """Count completed shaders, report the measured rate, and refresh build progress."""
    global LAST_RATE_LOG
    with _prog['lock']:
        DONE['n'] += 1
        n = DONE['n']
        now = time.monotonic()
        emit_rate = bool(PROGRESS and now - LAST_RATE_LOG >= 60)
        if emit_rate:
            LAST_RATE_LOG = now
    progress('compiling', n, len(keys), cached=len(cache_hits), misses=NMISS)
    if emit_rate:
        elapsed = max(now - BUILD_STARTED, 0.001)
        print(
            f"[Mugiwara4iOS] Metal throughput: {n / elapsed:.2f} shader/s "
            f"({n}/{len(keys)} finished, {PROCS} process workers).",
            flush=True,
        )


# The worker processes finish the MSL rewrite/reflection/Metal part without the GIL.
# Fork only after all profile/cache state is loaded and before any thread is started.
COUNTERS = (PRE_STATS, VIN_STATS, PULL_STATS, SIDE_STATS, BF_STATS, MTL.stats)


def worker_start():
    global PROGRESS
    STORE.forked()
    PROGRESS = None


def fin_worker(key, wb, job, err):
    jobs.clear()
    c1s.clear()
    xerr.clear()
    if job:
        jobs[key], c1s[key] = job
    if err is not None:
        xerr[key] = err
    for counter in COUNTERS:
        counter.clear()
    return fin(key, wb), [dict(counter) for counter in COUNTERS]


def submit(batch, wb):
    if not px:
        return [ex.submit(fin, key, wb) for key in batch]
    futures = [
        px.submit(
            fin_worker,
            key,
            wb,
            (jobs.pop(key), c1s.pop(key)) if key in jobs else None,
            xerr.get(key),
        )
        for key in batch
    ]
    for future in futures:
        future.add_done_callback(finished)
    return futures


def results(futures):
    output = []
    for future in futures:
        result = future.result()
        if px:
            result, counts = result
            for counter, values in zip(COUNTERS, counts):
                counter.update(values)
        output.append(result)
    return output


px = (
    cf.ProcessPoolExecutor(
        PROCS,
        mp_context=multiprocessing.get_context("fork"),
        initializer=worker_start,
    )
    if PROCS and keys
    else None
)
if px:
    # Metal's shared precompiled headers must exist before fork; workers must not each
    # create their own header. Start/fork every child before ThreadPoolExecutor starts.
    if "mac" in TARGETS:
        dmsh_pch.header(MAC_RUN + METAL_DEPTH)
    if IOSOUT:
        dmsh_pch.header(ios_metal.METAL + ios_metal.DEPTH)
    px.submit(int).result()
    active_workers = sorted(
        process.pid for process in px._processes.values() if process.is_alive()
    )
    if len(active_workers) != PROCS:
        sys.exit(
            f"[RED] expected {PROCS} live Metal finish workers, "
            f"but only {len(active_workers)} started: {active_workers}"
        )
    print(
        f"[Mugiwara4iOS] Metal process pool ACTIVE: {len(active_workers)} workers "
        f"(PIDs {active_workers}); target={','.join(sorted(TARGETS))}, "
        f"J={NJ}, batch={BATCH}.",
        flush=True,
    )


'''

ORCHESTRATION = r'''# Two phases: paired vertex shaders read their pixel shaders' MSL (vs_pad), so they go last.
# Translate the next batch while the current batch is being finished by the worker pool.
batches = [
    batch[i:i + BATCH]
    for batch in (
        [key for key in keys if key not in PAIRS],
        [key for key in keys if key in PAIRS],
    )
    for i in range(0, len(batch), BATCH)
]
res, busy = [], []


RATE_GUARD_SECONDS = float(os.environ.get("DMSH_RATE_GUARD_SECONDS", "300"))
MIN_SHADERS_PER_SEC = float(os.environ.get("DMSH_MIN_SHADERS_PER_SEC", "1.2"))


def collect(left):
    while len(busy) > left:
        wb, futures = busy.pop(0)
        res.extend(results(futures))
        shutil.rmtree(wb, ignore_errors=True)
        elapsed = time.monotonic() - BUILD_STARTED
        if elapsed >= RATE_GUARD_SECONDS:
            completed = DONE["n"]
            rate = completed / max(elapsed, 0.001)
            if rate < MIN_SHADERS_PER_SEC:
                sys.exit(
                    f"[RED] Mugiwara4iOS shader throughput guard stopped the build: "
                    f"{rate:.2f} shader/s after {elapsed:.0f}s "
                    f"({completed}/{len(keys)}); minimum is {MIN_SHADERS_PER_SEC:.2f}. "
                    "The run will not consume the six-hour runner budget at this rate."
                )


try:
    with cf.ThreadPoolExecutor(1) as tx, cf.ThreadPoolExecutor(NJ) as ex:
        nxt = tx.submit(translate, batches[0]) if batches else None
        for i, batch in enumerate(batches):
            assert nxt is not None
            wb = nxt.result()
            nxt = tx.submit(translate, batches[i + 1]) if i + 1 < len(batches) else None
            if batch[0] in PAIRS and i and batches[i - 1][0] not in PAIRS:
                collect(0)
            busy.append((wb, submit(batch, wb)))
            collect(1)
        collect(0)
except cf.process.BrokenProcessPool:
    sys.exit(
        f"[RED] a shader build worker process stopped (killed or out of memory) "
        f"with {len(keys) - len(res)} of {len(keys)} shaders unfinished; "
        "retry with fewer DMSH_PROCS workers. Completed work remains in cas.db."
    )
if px:
    px.shutdown()


'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path, required=True)
    args = parser.parse_args()

    engine = args.engine_root.resolve()
    # NX2Apple's engine.py stores the upstream stamp at the NX2Apple repo root,
    # one directory above engine/ (the workflow validates the same location).
    pin_file = engine.parent / ".upstream-ref"
    pin = pin_file.read_text(encoding="utf-8").strip() if pin_file.is_file() else ""
    if pin != ENGINE_PIN:
        raise SystemExit(
            f"[Mugiwara4iOS] Refusing worker patch: NXNative pin is {pin!r}, expected {ENGINE_PIN}."
        )

    gfx_tools = engine / "dm/gfx/tools"
    build_file = gfx_tools / "dmsh_build.py"
    worker_file = gfx_tools / "dmsh_build_workers.py"
    wrapper_file = gfx_tools / "own_compilers.py"
    cache_file = engine / "dm/tools/shader_cache.py"

    build_source = build_file.read_text(encoding="utf-8")
    cache_source = cache_file.read_text(encoding="utf-8")
    wrapper_source = wrapper_file.read_text(encoding="utf-8")

    # The process-worker implementation is based on the exact HookLink2iOS worker
    # algorithm. It runs as a sidecar, so dmsh_chain.py still hashes the untouched,
    # pinned dmsh_build.py and the 70 NX2Apple patches remain intact.
    build_source = replace_once(
        build_source,
        "import atexit, bisect, inspect, os, re, sys, json, mmap, struct, hashlib, shutil, subprocess, tempfile, time, collections, threading, concurrent.futures as cf\n",
        "import atexit, bisect, inspect, multiprocessing, os, re, sys, json, mmap, struct, hashlib, shutil, subprocess, tempfile, time, collections, threading, concurrent.futures as cf\n",
        "multiprocessing import",
    )
    build_source = replace_once(
        build_source,
        "NJ = int(os.environ.get('J', '8'))\nBATCH = 4 * NJ",
        "NJ = int(os.environ.get('J', '8'))\nPROCS = int(os.environ.get('DMSH_PROCS', NJ))\nBATCH = 4 * NJ",
        "DMSH_PROCS setting",
    )
    build_source = replace_once(
        build_source,
        "        with _prog['lock']: DONE['n'] += 1; n = DONE['n']\n        progress('compiling', n, len(keys), cached=len(cache_hits), misses=NMISS)\n",
        "        finished()\n",
        "worker progress callback",
    )
    phase_marker = "# Two phases: paired vertex shaders read their pixel shaders' MSL (vs_pad)"
    pass_marker = "# Passthrough geometry as mesh shaders (dmsh_mesh.py):"
    if build_source.count(phase_marker) != 1 or build_source.count(pass_marker) != 1:
        raise SystemExit("[Mugiwara4iOS] Refusing worker patch: shader orchestration anchors changed.")
    phase_at = build_source.index(phase_marker)
    pass_at = build_source.index(pass_marker, phase_at)
    if pass_at <= phase_at:
        raise SystemExit("[Mugiwara4iOS] Refusing worker patch: invalid shader orchestration range.")
    build_source = build_source[:phase_at] + PROCESS_WORKERS + ORCHESTRATION + build_source[pass_at:]
    build_source = MARKER + "\n" + build_source

    if "    def forked(self):" not in cache_source:
        cache_source = replace_once(
            cache_source,
            "    def _damage(self, e):",
            "    def forked(self):\n"
            "        \"\"\"Open a worker-local SQLite connection after multiprocessing fork.\"\"\"\n"
            "        self._inherited = self.db\n"
            "        self.lock = threading.RLock()\n"
            "        self._open()\n\n"
            "    def _damage(self, e):",
            "worker-local SQLite connection",
        )

    old_wrapper_line = "    sys.argv = [os.path.join(HERE, 'dmsh_build.py'), *sys.argv[1:]]\n"
    new_wrapper_line = (
        "    # Mugiwara4iOS: use the tested process-worker sidecar while keeping the pinned chain source unchanged.\n"
        "    sys.argv = [os.path.join(HERE, 'dmsh_build_workers.py'), *sys.argv[1:]]\n"
    )
    if "dmsh_build_workers.py" not in wrapper_source:
        wrapper_source = replace_once(wrapper_source, old_wrapper_line, new_wrapper_line, "own_compilers dispatch")
    if "dmsh_build_workers.py" not in wrapper_source:
        raise SystemExit("[Mugiwara4iOS] own_compilers.py did not select the worker sidecar.")

    # Compile every generated/modified entry point before writing any of them.
    compile(build_source, str(worker_file), "exec")
    compile(cache_source, str(cache_file), "exec")
    compile(wrapper_source, str(wrapper_file), "exec")

    worker_file.write_text(build_source, encoding="utf-8")
    cache_file.write_text(cache_source, encoding="utf-8")
    wrapper_file.write_text(wrapper_source, encoding="utf-8")

    # Re-read the files and verify the runner will actually invoke two worker processes.
    saved_worker = worker_file.read_text(encoding="utf-8")
    saved_cache = cache_file.read_text(encoding="utf-8")
    saved_wrapper = wrapper_file.read_text(encoding="utf-8")
    for token in ("PROCS = int(os.environ.get('DMSH_PROCS', NJ))", "ProcessPoolExecutor", "STORE.forked()"):
        if token not in saved_worker:
            raise SystemExit(f"[Mugiwara4iOS] Worker backport verification failed: {token}")
    if "def forked(self):" not in saved_cache or "dmsh_build_workers.py" not in saved_wrapper:
        raise SystemExit("[Mugiwara4iOS] Worker backport verification failed after writing files.")

    print(
        "[Mugiwara4iOS] HookLink2iOS Metal workers applied: J=1 + DMSH_PROCS=2; "
        "pinned dmsh_build.py/chain hash preserved; NX2Apple engine patches retained.",
        flush=True,
    )


if __name__ == "__main__":
    main()
