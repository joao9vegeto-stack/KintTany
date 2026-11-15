#!/usr/bin/env python3
"""Backport NXNative's GIL-free Metal finalizer and fork-safe cache broker to the pinned engine."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
MARKER = "# Mugiwara4iOS DMSH_PROCS worker backport"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"[Mugiwara4iOS] Refusing unsafe NXNative patch for {label}: "
            f"expected one anchor, found {count}."
        )
    return text.replace(old, new, 1)


PROCESS_WORKERS = r'''
BUILD_STARTED = time.monotonic()
LAST_RATE_LOG = BUILD_STARTED
LAST_RATE_COUNT = 0


def finished(*_):
    """Count completed shaders and report rolling/cumulative throughput without aborting."""
    global LAST_RATE_LOG, LAST_RATE_COUNT
    with _prog['lock']:
        DONE['n'] += 1
        n = DONE['n']
        now = time.monotonic()
        emit_rate = bool(PROGRESS and now - LAST_RATE_LOG >= 60)
        if emit_rate:
            interval = max(now - LAST_RATE_LOG, 0.001)
            interval_done = n - LAST_RATE_COUNT
            LAST_RATE_LOG = now
            LAST_RATE_COUNT = n
    progress('compiling', n, len(keys), cached=len(cache_hits), misses=NMISS)
    if emit_rate:
        elapsed = max(now - BUILD_STARTED, 0.001)
        rolling = interval_done / interval
        overall = n / elapsed
        print(
            f"[Mugiwara4iOS] Metal throughput: rolling={rolling:.2f} shader/s, "
            f"overall={overall:.2f} shader/s ({n}/{len(keys)} finished, "
            f"{PROCS} process workers).",
            flush=True,
        )


# The Python-heavy finalizer is run in independent processes rather than threads,
# so its MSL rewriting/reflection work is not serialized by one interpreter GIL.
# Workers are forked after all tables/cache keys are loaded and before build threads.
COUNTERS = (PRE_STATS, VIN_STATS, PULL_STATS, SIDE_STATS, BF_STATS, MTL.stats)


def worker_start():
    global PROGRESS, STORE
    assert SERVED is not None
    # Apple SQLite must remain in the parent process: children proxy cache calls
    # over their own pipe to a parent thread (NXNative issue #2354).
    STORE = MTL.store = SERVED.worker()
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


def _prime_worker():
    # Keep tasks alive briefly so every process is started before the pool check.
    time.sleep(0.75)
    return os.getpid()


SERVED = shader_cache.Served(STORE, PROCS) if PROCS and keys else None
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
    # Precompile the shared Metal PCH in the parent; a child-created PCH would
    # be duplicated per worker and left behind when that worker exits.
    if "mac" in TARGETS:
        dmsh_pch.header(MAC_RUN + METAL_DEPTH)
    if IOSOUT:
        dmsh_pch.header(ios_metal.METAL + ios_metal.DEPTH)
    prime = [px.submit(_prime_worker) for _ in range(PROCS)]
    worker_pids = sorted({future.result() for future in prime})
    if len(worker_pids) != PROCS:
        sys.exit(
            f"[RED] Mugiwara4iOS requested {PROCS} Metal finish workers, "
            f"but only {len(worker_pids)} distinct workers started: {worker_pids}."
        )
    assert SERVED is not None
    SERVED.start()
    print(
        f"[Mugiwara4iOS] Metal process pool ACTIVE: {len(worker_pids)} workers "
        f"(PIDs {worker_pids}); fork-safe SQLite broker ACTIVE; "
        f"J={NJ}, batch={BATCH}, target={','.join(sorted(TARGETS))}.",
        flush=True,
    )


''';

ORCHESTRATION = r'''# Two phases: paired vertex shaders read their pixel shaders' MSL (vs_pad), so they go last.
# Translate the next batch while the current batch is being finalized by the worker pool.
batches = [
    batch[i:i + BATCH]
    for batch in (
        [key for key in keys if key not in PAIRS],
        [key for key in keys if key in PAIRS],
    )
    for i in range(0, len(batch), BATCH)
]
res, busy = [], []


def collect(left):
    while len(busy) > left:
        wb, futures = busy.pop(0)
        res.extend(results(futures))
        shutil.rmtree(wb, ignore_errors=True)


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
except BrokenProcessPool as exc:
    sys.exit(
        f"[RED] a Metal shader finish worker process stopped (killed or out of memory): "
        f"{exc}; {len(keys) - len(res)} shaders remain unfinished. "
        "The cache broker keeps SQLite in the parent; reduce DMSH_PROCS only if "
        "the runner actually runs out of memory."
    )
if px:
    px.shutdown()


''';


SERVED_CLASSES = r'''

# Mugiwara4iOS backport of NXNative's fork-safe cache broker (issue #2354).
# Only the parent process owns the SQLite connection; forked workers send calls
# through one pipe each. This avoids Apple's SQLite os_signpost crash after fork.
class _Gone(Exception):
    pass


class _Abort(Exception):
    pass


class Served:
    OPS = ('get', 'has', 'names', 'put', 'delete_prefix')

    def __init__(self, store, n):
        ctx = multiprocessing.get_context('fork')
        self.store = store
        self.pipes = [ctx.Pipe() for _ in range(n)]
        self.taken = ctx.Value('i', 0)

    def start(self):
        for here, there in self.pipes:
            there.close()
            threading.Thread(target=self._serve, args=(here,), daemon=True).start()

    def worker(self):
        with self.taken.get_lock():
            i = self.taken.value
            self.taken.value += 1
        for j, (here, there) in enumerate(self.pipes):
            here.close()
            if j != i:
                there.close()
        return Remote(self.pipes[i][1])

    def _serve(self, conn):
        with contextlib.suppress(_Gone, EOFError, OSError):
            self._calls(conn, False)

    def _calls(self, conn, inside):
        store = self.store
        while True:
            try:
                op, args = conn.recv()
            except (EOFError, OSError):
                if inside:
                    raise _Gone from None
                return
            if op == 'end' and inside:
                return
            if op == 'abort' and inside:
                raise _Abort
            try:
                if op == 'begin' and not inside:
                    try:
                        with store.batch():
                            conn.send((True, None, store.full))
                            self._calls(conn, True)
                    except _Abort:
                        pass
                    value = None
                elif op in self.OPS:
                    value = getattr(store, op)(*args)
                else:
                    raise ValueError(f'shader cache: no call {op!r}')
            except _Gone:
                raise
            except Exception as exc:
                conn.send((False, exc, store.full))
            else:
                conn.send((True, value, store.full))


class Remote:
    def __init__(self, conn):
        self.conn = conn
        self.lock = threading.RLock()
        self.inside = False
        self.full = False

    def _call(self, op, *args):
        with self.lock:
            self.conn.send((op, args))
            ok, value, self.full = self.conn.recv()
        if not ok:
            raise value
        return value

    def get(self, name):
        return self._call('get', name)

    def has(self, name):
        return self._call('has', name)

    def names(self, prefix):
        return self._call('names', prefix)

    def put(self, name, data, when=None):
        self._call('put', name, data, when)

    def put_file(self, name, path):
        with open(path, 'rb') as stream:
            self.put(name, stream.read())

    def to_file(self, name, path):
        data = self.get(name)
        if data is None:
            return False
        tmp = f'{path}.tmp-{os.getpid()}-{threading.get_ident()}'
        with open(tmp, 'wb') as stream:
            stream.write(data)
        os.replace(tmp, path)
        return True

    def delete_prefix(self, prefix):
        self._call('delete_prefix', prefix)

    @contextlib.contextmanager
    def batch(self):
        with self.lock:
            if self.inside:
                yield
                return
            self._call('begin')
            self.inside = True
            try:
                yield
            except BaseException:
                self.inside = False
                self._call('abort')
                raise
            else:
                self.inside = False
                self._call('end')

'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path, required=True)
    args = parser.parse_args()

    engine = args.engine_root.resolve()
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

    if MARKER in build_source:
        raise SystemExit("[Mugiwara4iOS] Refusing to patch the upstream dmsh_build.py in place.")

    if worker_file.is_file() and "dmsh_build_workers.py" in wrapper_source:
        required = (
            "ProcessPoolExecutor",
            "shader_cache.Served(STORE, PROCS)",
            "STORE = MTL.store = SERVED.worker()",
            "SERVED.start()",
            "BrokenProcessPool",
            "rolling={rolling:.2f} shader/s",
        )
        saved = worker_file.read_text(encoding="utf-8")
        missing = [token for token in required if token not in saved]
        if missing or "STORE.forked()" in saved or "DMSH_RATE_GUARD_SECONDS" in saved:
            raise SystemExit(
                f"[Mugiwara4iOS] Existing worker sidecar is outdated/incomplete: "
                f"missing={missing}, direct_sqlite={'STORE.forked()' in saved}, "
                f"hard_rate_guard={'DMSH_RATE_GUARD_SECONDS' in saved}."
            )
        if "class Served:" not in cache_source or "class Remote:" not in cache_source:
            raise SystemExit("[Mugiwara4iOS] Existing cache broker classes are missing.")
        print("[Mugiwara4iOS] Verified existing GIL-free workers and fork-safe cache broker.", flush=True)
        return

    old_import = (
        "import atexit, bisect, inspect, os, re, sys, json, mmap, struct, hashlib, "
        "shutil, subprocess, tempfile, time, collections, threading, concurrent.futures as cf\n"
    )
    new_import = (
        "import atexit, bisect, inspect, multiprocessing, os, re, sys, json, mmap, struct, "
        "hashlib, shutil, subprocess, tempfile, time, collections, threading, "
        "concurrent.futures as cf\n"
        "from concurrent.futures.process import BrokenProcessPool\n"
    )
    build_source = replace_once(build_source, old_import, new_import, "multiprocessing imports")
    build_source = replace_once(
        build_source,
        "NJ = int(os.environ.get('J', '8'))\nBATCH = 4 * NJ",
        "NJ = int(os.environ.get('J', '8'))\n"
        "PROCS = int(os.environ.get('DMSH_PROCS', NJ))\nBATCH = 4 * NJ",
        "DMSH_PROCS setting",
    )
    build_source = replace_once(
        build_source,
        "        with _prog['lock']: DONE['n'] += 1; n = DONE['n']\n"
        "        progress('compiling', n, len(keys), cached=len(cache_hits), misses=NMISS)\n",
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
    build_source = (
        build_source[:phase_at] + MARKER + "\n" + PROCESS_WORKERS + ORCHESTRATION
        + build_source[pass_at:]
    )

    cache_import = (
        "import contextlib, hashlib, json, os, re, shutil, sqlite3, tarfile, threading, time\n"
    )
    cache_import_new = (
        "import contextlib, hashlib, json, multiprocessing, os, re, shutil, sqlite3, "
        "tarfile, threading, time\n"
    )
    cache_source = replace_once(cache_source, cache_import, cache_import_new, "cache multiprocessing import")
    if "class Served:" not in cache_source and "class Remote:" not in cache_source:
        cache_source = cache_source.rstrip() + "\n" + SERVED_CLASSES
    elif not ("class Served:" in cache_source and "class Remote:" in cache_source):
        raise SystemExit("[Mugiwara4iOS] Refusing partial/ambiguous Served cache broker patch.")

    old_wrapper_line = "    sys.argv = [os.path.join(HERE, 'dmsh_build.py'), *sys.argv[1:]]\n"
    new_wrapper_line = (
        "    # Mugiwara4iOS: use GIL-free finish workers; keep the pinned chain file intact.\n"
        "    sys.argv = [os.path.join(HERE, 'dmsh_build_workers.py'), *sys.argv[1:]]\n"
    )
    if "dmsh_build_workers.py" not in wrapper_source:
        wrapper_source = replace_once(wrapper_source, old_wrapper_line, new_wrapper_line, "own_compilers dispatch")
    if "dmsh_build_workers.py" not in wrapper_source:
        raise SystemExit("[Mugiwara4iOS] own_compilers.py did not select the worker sidecar.")

    compile(build_source, str(worker_file), "exec")
    compile(cache_source, str(cache_file), "exec")
    compile(wrapper_source, str(wrapper_file), "exec")

    worker_file.write_text(build_source, encoding="utf-8")
    cache_file.write_text(cache_source, encoding="utf-8")
    wrapper_file.write_text(wrapper_source, encoding="utf-8")

    saved_worker = worker_file.read_text(encoding="utf-8")
    saved_cache = cache_file.read_text(encoding="utf-8")
    saved_wrapper = wrapper_file.read_text(encoding="utf-8")
    for token in (
        "PROCS = int(os.environ.get('DMSH_PROCS', NJ))",
        "ProcessPoolExecutor",
        "shader_cache.Served(STORE, PROCS)",
        "STORE = MTL.store = SERVED.worker()",
        "SERVED.start()",
        "BrokenProcessPool",
        "rolling={rolling:.2f} shader/s",
    ):
        if token not in saved_worker:
            raise SystemExit(f"[Mugiwara4iOS] Worker backport verification failed: {token}")
    if "DMSH_RATE_GUARD_SECONDS" in saved_worker or "STORE.forked()" in saved_worker:
        raise SystemExit("[Mugiwara4iOS] Unsafe direct-SQLite worker or fixed-rate abort remains.")
    if not ("import multiprocessing" in saved_cache and "class Served:" in saved_cache
            and "class Remote:" in saved_cache):
        raise SystemExit("[Mugiwara4iOS] Fork-safe cache broker verification failed.")
    if "dmsh_build_workers.py" not in saved_wrapper:
        raise SystemExit("[Mugiwara4iOS] own_compilers.py dispatch verification failed.")

    print(
        "[Mugiwara4iOS] GIL-free finish workers and fork-safe Served/Remote cache broker applied; "
        "upstream dmsh_build.py and the pinned translation chain remain unchanged.",
        flush=True,
    )


if __name__ == "__main__":
    main()
