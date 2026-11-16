#!/usr/bin/env python3
"""Install Mugiwara's bounds-safe Metal uniform guards into the NXNative worker sidecar."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
WORKER_MARKER = "# Mugiwara4iOS DMSH_PROCS worker backport"
GUARD_MARKER = "# Mugiwara4iOS bounds-safe uniform guard rewrite"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(
            f"[Mugiwara4iOS] Refusing guard patch for {label}: expected one anchor, found {count}."
        )
    return source.replace(old, new, 1)


def patch_worker_source(source: str) -> str:
    if WORKER_MARKER not in source:
        raise SystemExit("[Mugiwara4iOS] GIL-free worker sidecar marker is missing.")
    if GUARD_MARKER in source:
        required = (
            "mugiwara_guard_rewrite.select_guards_with_stats",
            "_MUGIWARA_GUARD_COUNTS",
            "Guard rewrite totals: shaders=%d",
        )
        missing = [token for token in required if token not in source]
        if missing:
            raise SystemExit(f"[Mugiwara4iOS] Existing partial guard patch: missing {missing}.")
        compile(source, "<dmsh_build_workers.py>", "exec")
        return source

    source = replace_once(
        source,
        "import dmsh_geometry,",
        "import mugiwara_guard_rewrite, dmsh_geometry,",
        "uniform guard helper import",
    )
    source = replace_once(
        source,
        "\ndef finish(key, w, j, c1):\n",
        "\n" + GUARD_MARKER + "\n"
        "_MUGIWARA_GUARD_COUNTS = collections.Counter()\n"
        "\ndef finish(key, w, j, c1):\n",
        "uniform guard counter",
    )
    precise_anchor = (
        "    src = precise(src)   # min / max / clamp with Maxwell's NaN results (see precise)\n"
    )
    guard_hook = (
        precise_anchor
        + "    _mugi_guard_src, _mugi_guard_dynamic, _mugi_guard_fixed = "
          "mugiwara_guard_rewrite.select_guards_with_stats(src)\n"
        + "    if _mugi_guard_src != src:\n"
        + "        _MUGIWARA_GUARD_COUNTS.update(shaders=1, dynamic_index=_mugi_guard_dynamic, "
          "fixed_index=_mugi_guard_fixed)\n"
        + "        src = _mugi_guard_src\n"
    )
    source = replace_once(source, precise_anchor, guard_hook, "safe-index uniform rewrite")
    source = replace_once(
        source,
        "COUNTERS = (PRE_STATS, VIN_STATS, PULL_STATS, SIDE_STATS, BF_STATS, MTL.stats)",
        "COUNTERS = (PRE_STATS, VIN_STATS, PULL_STATS, SIDE_STATS, BF_STATS, MTL.stats, "
        "_MUGIWARA_GUARD_COUNTS)",
        "worker guard counter aggregation",
    )
    source = replace_once(
        source,
        "if px:\n    px.shutdown()\n",
        "if px:\n    px.shutdown()\n"
        "print('[Mugiwara4iOS] Guard rewrite totals: shaders=%d dynamic_index=%d fixed_index=%d' % "
        "(_MUGIWARA_GUARD_COUNTS['shaders'], _MUGIWARA_GUARD_COUNTS['dynamic_index'], "
        "_MUGIWARA_GUARD_COUNTS['fixed_index']), flush=True)\n",
        "guard summary",
    )
    compile(source, "<dmsh_build_workers.py>", "exec")
    return source


def self_test() -> None:
    fixture = (
        "import collections\n"
        "import dmsh_geometry, dmsh_atomic\n"
        f"{WORKER_MARKER}\n"
        "def finish(key, w, j, c1):\n"
        "    src = precise(src)   # min / max / clamp with Maxwell's NaN results (see precise)\n"
        "    return src\n"
        "COUNTERS = (PRE_STATS, VIN_STATS, PULL_STATS, SIDE_STATS, BF_STATS, MTL.stats)\n"
        "if px:\n"
        "    px.shutdown()\n"
    )
    patched = patch_worker_source(fixture)
    assert "mugiwara_guard_rewrite.select_guards_with_stats(src)" in patched
    assert "_MUGIWARA_GUARD_COUNTS)," in patched
    assert "Guard rewrite totals: shaders=%d" in patched
    assert patch_worker_source(patched) == patched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path, required=True)
    args = parser.parse_args()

    engine = args.engine_root.resolve()
    pin_file = engine.parent / ".upstream-ref"
    pin = pin_file.read_text(encoding="utf-8").strip() if pin_file.is_file() else ""
    if pin != ENGINE_PIN:
        raise SystemExit(
            f"[Mugiwara4iOS] Refusing guard patch: NXNative pin is {pin!r}, expected {ENGINE_PIN}."
        )

    tools_dir = engine / "dm/gfx/tools"
    worker_file = tools_dir / "dmsh_build_workers.py"
    helper_file = tools_dir / "mugiwara_guard_rewrite.py"
    helper_source_file = Path(__file__).with_name("mugiwara_uniform_rewrite.py")
    if not worker_file.is_file():
        raise SystemExit("[Mugiwara4iOS] GIL-free worker sidecar was not created before guard patch.")
    if not helper_source_file.is_file():
        raise SystemExit(f"[Mugiwara4iOS] Safe-index helper is missing: {helper_source_file}")

    helper_source = helper_source_file.read_text(encoding="utf-8")
    helper_module = compile(helper_source, str(helper_file), "exec")
    del helper_module
    worker_source = worker_file.read_text(encoding="utf-8")
    patched_worker = patch_worker_source(worker_source)

    compile(helper_source, str(helper_file), "exec")
    compile(patched_worker, str(worker_file), "exec")
    helper_file.write_text(helper_source, encoding="utf-8")
    worker_file.write_text(patched_worker, encoding="utf-8")

    saved = worker_file.read_text(encoding="utf-8")
    helper_saved = helper_file.read_text(encoding="utf-8")
    for token in (
        GUARD_MARKER,
        "mugiwara_guard_rewrite.select_guards_with_stats",
        "_MUGIWARA_GUARD_COUNTS",
        "Guard rewrite totals: shaders=%d",
    ):
        if token not in saved:
            raise SystemExit(f"[Mugiwara4iOS] Safe-index guard verification failed: {token}")
    if "def select_guards_with_stats" not in helper_saved:
        raise SystemExit("[Mugiwara4iOS] Installed safe-index helper is incomplete.")
    print(
        "[Mugiwara4iOS] Bounds-safe uniform select guards installed in the GIL-free worker sidecar; "
        "the upstream engine source and shader-chain pin remain untouched.",
        flush=True,
    )


if __name__ == "__main__":
    main()
