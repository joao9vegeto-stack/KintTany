#!/usr/bin/env python3
"""Selective host-only backport of NXNative PR #2919 for Kakarot.

The engine remains pinned to the exact NXNative revision used to produce the
cached Kakarot shader package. Only the six NVN runtime source files changed
by PR #2919 are three-way-applied; no game profile, shader table, chain file,
translator, or compiled Metal library is updated.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
UPSTREAM_PARENT = "3fe574dfe06638996d6fbaf80275253db47b86b9"
UPSTREAM_COMMIT = "23427a7befb6662fec04aa810e0713e5c8d1dd96"
FILES = (
    "dm/gfx/nvn/hle_nvn.c",
    "dm/gfx/nvn/nvn_dirty.c",
    "dm/gfx/nvn/nvn_dirty.h",
    "dm/gfx/nvn/nvn_geometry.inc",
    "dm/gfx/nvn/nvn_mtl.m",
    "dm/gfx/nvn/nvn_obj.h",
)
REQUIRED = {
    "dm/gfx/nvn/hle_nvn.c": ("vpt_walk_locked", "nvn_buffer_write_ranges"),
    "dm/gfx/nvn/nvn_dirty.c": ("nvn_dirty_gpu_written", "own_note();"),
    "dm/gfx/nvn/nvn_dirty.h": ("nvn_dirty_gpu_written",),
    "dm/gfx/nvn/nvn_geometry.inc": ("g_read_ev.signaledValue < g_read_v",),
    "dm/gfx/nvn/nvn_mtl.m": (
        "POST_BUFFER_COPY", "post_buffer_copy(", "buffer_copy_note(",
        "gpu_read_wait(", "tex_cpu_wait(", "b2b_flush(",
        "nvn_buffer_write_ranges(dst, n, buffer_copy_note)",
        "nvn_dirty_gpu_written(g_b2b_lo[i]",
        "pk->own == nvn_dirty_own_writes()",
        "s->wown != nvn_dirty_own_writes()",
    ),
    "dm/gfx/nvn/nvn_obj.h": ("nvn_buffer_range_fn", "nvn_buffer_write_ranges"),
}


def run(argv: list[str], cwd: Path | None = None, *, capture: bool = True) -> str:
    p = subprocess.run(
        argv, cwd=cwd, text=True, stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None, check=False,
    )
    output = p.stdout or "" if capture else ""
    if p.returncode:
        raise SystemExit(
            f"[KaKaRoTiOS] GPU-copy ordering backport command failed "
            f"({p.returncode}): {' '.join(argv)}\n{output[-12000:]}"
        )
    return output


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"[KaKaRoTiOS] GPU-copy ordering backport refused: {message}")


def self_test() -> None:
    assert len(FILES) == 6 and len(set(FILES)) == 6
    assert set(REQUIRED) == set(FILES)
    assert UPSTREAM_PARENT != ENGINE_PIN and UPSTREAM_COMMIT != UPSTREAM_PARENT
    assert all(REQUIRED.values())
    print("[KaKaRoTiOS] PR #2919 backport contract: six NVN runtime files only; shader assets excluded.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.engine_root is None:
        parser.error("--engine-root is required unless --self-test is used")

    engine = args.engine_root.resolve()
    root = Path(run(["git", "-C", str(engine), "rev-parse", "--show-toplevel"]).strip()).resolve()
    pin_file = engine.parent / ".upstream-ref"
    pin = pin_file.read_text(encoding="utf-8").strip() if pin_file.is_file() else ""
    if pin != ENGINE_PIN:
        fail(f"NXNative engine pin is {pin!r}; expected {ENGINE_PIN}.")
    head = run(["git", "-C", str(root), "rev-parse", "HEAD"]).strip()
    if head != ENGINE_PIN:
        fail(f"checked-out NXNative HEAD is {head}, expected {ENGINE_PIN}; refusing an unreviewed base.")
    dirty = run(["git", "-C", str(root), "status", "--porcelain"]).strip()
    if dirty:
        fail("NXNative worktree is not clean before the backport:\n" + dirty[:6000])

    print(
        f"[KaKaRoTiOS] Selective NVN runtime backport: {UPSTREAM_COMMIT} "
        f"(parent {UPSTREAM_PARENT}) onto pinned {ENGINE_PIN}.",
        flush=True,
    )
    run([
        "git", "-C", str(root), "fetch", "--no-tags",
        "https://github.com/seedds/nxnative.git",
        UPSTREAM_PARENT, UPSTREAM_COMMIT,
    ])
    patch = run([
        "git", "-C", str(root), "diff", "--binary",
        UPSTREAM_PARENT, UPSTREAM_COMMIT, "--", *FILES,
    ])
    if not patch.strip():
        fail("upstream PR #2919 produced an empty runtime patch.")
    # Three-way application uses the PR's exact parent blobs and the pinned
    # engine as the merge side. It fails closed on any ambiguous/conflicting hunk.
    apply = subprocess.run(
        ["git", "-C", str(root), "apply", "--3way", "--index", "-"],
        input=patch, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False,
    )
    if apply.returncode:
        run(["git", "-C", str(root), "reset", "--hard", ENGINE_PIN])
        fail(
            "PR #2919 does not merge cleanly onto the pinned Kakarot engine; "
            "no partial source patch will be built.\n" + (apply.stdout or "")[-12000:]
        )

    changed = set(run([
        "git", "-C", str(root), "diff", "--cached", "--name-only",
    ]).splitlines())
    if changed != set(FILES):
        run(["git", "-C", str(root), "reset", "--hard", ENGINE_PIN])
        fail(f"unexpected modified-file set: {sorted(changed)}")
    for rel, markers in REQUIRED.items():
        source = (root / rel).read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in source]
        if missing:
            run(["git", "-C", str(root), "reset", "--hard", ENGINE_PIN])
            fail(f"{rel}: required PR #2919 implementation markers missing: {missing}")

    print("[KaKaRoTiOS] PR #2919 runtime code merged cleanly and all implementation markers verified.", flush=True)
    print("[KaKaRoTiOS] Changed files: " + ", ".join(sorted(changed)), flush=True)
    print("[KaKaRoTiOS] Shader map, shader pairs, DMSH_CHAIN, dmsh_build, Metal image and game profile remain untouched.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
