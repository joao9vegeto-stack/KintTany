#!/usr/bin/env python3
"""Backport independent nxnative changes without losing the official NX2Apple patch queue.

A skipped change is NOT silently force-applied; each accepted change is exported
as a new patch, re-applied from the original NX2Apple pin, and validated by CI.
This deliberately does not change .upstream-ref or claim nxnative HEAD parity.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"
UPSTREAM = "https://github.com/seedds/nxnative.git"
SPECS = [["7dacea9c9a56d13f62599a80d92fa201c5f37713","Correct OpenGL packed pixel uploads",["dm/gfx/gl/hle_gl.m","dm/gfx/tests/t_gl_imports.m"]],["4b92e2322747ce8113ce34af63e1ad040e084c55","Synchronize HID controller style binding",["dm/host/hle_hid.c","dm/host/tests/t_hid.c"]],["4815cbbf84efc59827b8d00402b10287340a7198","Stage changed iOS RomFS and shader images atomically",["dm/ios/tools/stage_resources.sh","dm/ios/tests/test_xcode_workflow.py"]],["538da5d912518d2e2e8af24880a7aeb37ea99693","Keep relative thread waits independent of replay clock",["dm/host/dm.h","dm/host/hle.h","dm/host/hle_os.c","dm/host/hle_thread.c","dm/host/tests/Makefile","dm/host/tests/t_condvar_stub.c","dm/host/tests/t_objmap.c","dm/host/tests/t_sync_wait.c","dm/gfx/tests/Makefile","dm/gfx/tests/t_counter_clock.m"]],["93c76c1cbf4121f2609f24eaa0d2cafec9bb04c7","Trim idle Metal staging buffers on opt in",["dm/gfx/nvn/nvn_mtl.m","dm/gfx/tests/Makefile","dm/gfx/tests/t_upload_idle.m"]],["943a6111540e17333f7e060f40248ad68d62dce5","Limit oversized render target heap reuse slack",["dm/gfx/nvn/nvn_mtl.m","dm/gfx/tests/t_rt_recycle.m"]],["1d1c5b4afbe9ea8e5d3a67f6a8aa662fb92b864d","Bound NVN zero fills to the shared Metal buffer",["dm/gfx/nvn/nvn_mtl.m","dm/gfx/tests/Makefile","dm/gfx/tests/t_lazy_clear_order.m","dm/gfx/tests/t_zero_colour.m"]],["31fdefeb4e9169e4ca904a4625f94d3c38c328a4","Budget zero copy upload sources per batch",["dm/gfx/nvn/nvn_mtl.m","dm/gfx/tests/Makefile","dm/gfx/tests/t_upload_src.m"]],["950212b9fc9033bb212141c7334c611b48d00e7b","Track CPU writes to compressed sparse textures",["dm/gfx/nvn/nvn_mtl.m","dm/gfx/tests/t_initial_uncached.m"]],["b95a6b247daaf9b776d0df3d819f1edee00004ce","Wait for frame producer when capturing screenshots",["dm/gfx/nvn/nvn_mtl.m","dm/gfx/tests/Makefile","dm/gfx/tests/t_present_crop.m"]]]

def run(*argv, cwd=ROOT, data=None, checked=True):
    p = subprocess.run(argv, cwd=cwd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if checked and p.returncode:
        raise RuntimeError(f"{' '.join(argv)}: {p.stderr.decode(errors='replace')[-1800:]}")
    return p

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    if len(args.target) != 40 or any(ch not in "0123456789abcdef" for ch in args.target):
        parser.error("Specify a pinned 40-character nxnative commit")
    if not (ENGINE / ".git").exists():
        raise RuntimeError("Materialize the pinned engine with tools/engine.py sync first")
    if run("git", "status", "--porcelain", cwd=ENGINE).stdout.strip():
        raise RuntimeError("Refusing to overwrite an engine checkout with local changes")
    print(f"Fetching upstream ancestry for selected target {args.target}", flush=True)
    run("git", "fetch", "--no-tags", "--depth=90", UPSTREAM, args.target, cwd=ENGINE)
    accepted, skipped = [], []
    for sha, title, paths in SPECS:
        before = run("git", "rev-parse", "HEAD", cwd=ENGINE).stdout.decode().strip()
        diff = run("git", "diff", "--full-index", "--binary", sha + "^", sha, "--", *paths, cwd=ENGINE).stdout
        if not diff:
            skipped.append((sha, title, "No selected generic code changes"))
            continue
        applied = run("git", "apply", "--3way", "--index", "-", cwd=ENGINE, data=diff, checked=False)
        if applied.returncode:
            conflict = run("git", "diff", "--name-only", "--diff-filter=U", cwd=ENGINE).stdout.decode().strip()
            error = applied.stderr.decode(errors="replace")[-400:].strip()
            skipped.append((sha, title, conflict or error or "Patch does not apply"))
            run("git", "reset", "--hard", before, cwd=ENGINE)
            run("git", "clean", "-fd", cwd=ENGINE)
            print(f"DEFERRED {sha[:12]}: {title}: {conflict or error}", flush=True)
            continue
        if run("git", "diff", "--cached", "--quiet", cwd=ENGINE, checked=False).returncode == 0:
            skipped.append((sha, title, "Already present"))
            print(f"ALREADY PRESENT {sha[:12]}", flush=True)
            continue
        run("git", "diff", "--cached", "--check", cwd=ENGINE)
        run("git", "-c", "user.name=dante2ios-upstream-backport",
            "-c", "user.email=dante2ios-upstream-backport@users.noreply.github.com",
            "commit", "--quiet", "-m", f"Dante2iOS: nxnative {sha[:12]} - {title}", cwd=ENGINE)
        # A patch export checks the NX2Apple chain-protection policy; fail instead of bypassing it.
        run(sys.executable, "tools/engine.py", "export", "HEAD", "--status", "pending",
            "--reason", f"Isolated nxnative runtime fix: {title}; full HEAD rebase remains blocked by shared-shell conflicts",
            "--issue", f"seedds/nxnative@{sha}")
        accepted.append((sha, title))
        print(f"APPLIED {sha[:12]}: {title}", flush=True)
    print(f"BACKPORT RESULT: {len(accepted)} of {len(SPECS)} candidate improvements", flush=True)
    for sha, title, reason in skipped:
        print(f"DEFERRED {sha[:12]}: {title}: {reason}", flush=True)
    ghout = os.environ.get("GITHUB_OUTPUT")
    if ghout:
        with open(ghout, "a", encoding="utf-8") as f:
            f.write(f"count={len(accepted)}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## Selective nxnative backports\n\n{len(accepted)} of {len(SPECS)} candidates applied. The original 56 patches remain intact and the engine pin is unchanged.\n\n")
            for sha, title in accepted:
                f.write(f"- Applied \`{sha[:12]}\`: {title}\n")
            for sha, title, reason in skipped:
                f.write(f"- Deferred \`{sha[:12]}\`: {title} — {reason}\n")
    if not accepted:
        print("No safe backport could be applied; no engine changes will be committed.", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("BACKPORT FAILED: " + str(e), file=sys.stderr)
        sys.exit(2)
