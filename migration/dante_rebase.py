#!/usr/bin/env python3
"""Rebase Dante2iOS's branch-local Steam/controller patch with real Git blob ancestry.

NX2Apple's queue is first replayed on its declared old pin. That materializes the
exact preimage and postimage blobs for patch 0017. Their hashes are then written
into a temporary copy of that patch so git am -3 can perform a genuine three-way
merge onto current nxnative main. The queue is committed to the checkout only
after every patch has replayed successfully.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


PATCH_NAME = "0017-support-steam-controller-and-shared-mac-control.patch"
QUEUE_BASE = "0b5fd6020093407af8bb5ad166e78e00bd2b7242"
PR_COMMIT = "6a585be66dbfdd02c2ff5e0a39c51cc03f7e8dbb"
PR_PARENT = "72047f1aa94f42f6f8d359e4934787304d85d5cc"
PR_REF = "refs/dante2ios/pr-221"


def git(P, *args: str, cwd: Path, check: bool = True):
    return P.git(*args, cwd=cwd, check=check)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--to", required=True, help="full nxnative commit SHA resolved from main")
    ap.add_argument("--tmp", type=Path, required=True)
    args = ap.parse_args()

    root = args.repo.resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", args.to):
        raise SystemExit("--to must be a full 40-character commit SHA")

    sys.path.insert(0, str(root / "tools"))
    import engine as E
    import patches as P

    nx2apple_pin = E.pin(root)
    if nx2apple_pin != "94a0944755da1a443f42651bf7ee49ab24ed5ee5":
        raise SystemExit(
            f"Unexpected NX2Apple source pin {nx2apple_pin}; "
            "the checked-in frontend snapshot has changed"
        )
    queue_base = QUEUE_BASE
    queue = P.load(root)
    positions = [i for i, patch in enumerate(queue) if patch.file == PATCH_NAME]
    if len(positions) != 1:
        raise SystemExit(f"Expected exactly one {PATCH_NAME} in patches/series")
    position = positions[0]
    steam_patch = queue[position]

    engine_repo = E.scratch_root(root)
    E.fetch(engine_repo, nx2apple_pin)
    E.fetch(engine_repo, args.to)
    E.fetch(engine_repo, queue_base)

    # tools/engine.py intentionally fetches each commit at depth 1. The queue
    # uses intermediate preimages, so the full target history is required.
    upstream_url = os.environ.get("NX2APPLE_ENGINE_URL") or E.UPSTREAM_URL
    shallow = git(P, "rev-parse", "--is-shallow-repository", cwd=engine_repo).stdout.strip()
    if shallow == "true":
        deepened = git(
            P, "fetch", "--quiet", "--no-tags", "--unshallow",
            upstream_url, args.to, cwd=engine_repo, check=False,
        )
        if deepened.returncode:
            detail = (deepened.stdout + deepened.stderr).strip()
            raise SystemExit(
                "Could not fetch complete nxnative history needed for three-way merge. "
                + detail[-5000:]
            )
    shallow = git(P, "rev-parse", "--is-shallow-repository", cwd=engine_repo).stdout.strip()
    if shallow != "false":
        raise SystemExit("nxnative object database is still shallow; refusing an incomplete rebase")
    print(f"Fetched complete nxnative history through {args.to}.", flush=True)

    ancestor = git(
        P, "merge-base", "--is-ancestor", queue_base, args.to,
        cwd=engine_repo, check=False,
    )
    if ancestor.returncode:
        raise SystemExit(f"Queue preparation base {queue_base} is not an ancestor of target {args.to}")

    # Fetch and pin the original PR head. Its real parent/postimage allow Git
    # to perform a true three-way merge; the hand-edited mail patch has stale
    # textual context after the branch-local queue was transplanted.
    pr_fetch = git(
        P, "fetch", "--quiet", "--no-tags",
        "https://github.com/seedds/nxnative.git",
        f"+refs/pull/221/head:{PR_REF}",
        cwd=engine_repo, check=False,
    )
    if pr_fetch.returncode:
        detail = (pr_fetch.stdout + pr_fetch.stderr).strip()
        raise SystemExit("Could not fetch seedds/nxnative PR #221 head. " + detail[-5000:])
    pr_sha = git(P, "rev-parse", PR_REF, cwd=engine_repo).stdout.strip()
    if pr_sha != PR_COMMIT:
        raise SystemExit(f"PR #221 head changed: expected {PR_COMMIT}, fetched {pr_sha}")
    pr_parent = git(P, "rev-parse", f"{pr_sha}^", cwd=engine_repo).stdout.strip()
    if pr_parent != PR_PARENT:
        raise SystemExit(f"PR #221 parent changed: expected {PR_PARENT}, found {pr_parent}")
    if git(P, "merge-base", "--is-ancestor", pr_parent, args.to,
           cwd=engine_repo, check=False).returncode:
        raise SystemExit(f"PR #221 parent {pr_parent} is not an ancestor of target {args.to}")
    print(f"Verified original PR #221 commit {pr_sha} with parent {pr_parent}.", flush=True)

    # Verify that patches 0001-0016 reproduce the recorded preparation base
    # before attempting the current-main rebase.
    with P.Scratch(engine_repo, queue_base, args.tmp) as base:
        prior_applied, prior_landed, prior_conflicts = P.apply_series(base.dir, queue[:position])
        if prior_conflicts:
            P.report(queue_base, queue_base, prior_applied, prior_landed, prior_conflicts)
            raise SystemExit(f"The queue does not reproduce preparation base {queue_base}")
        print(
            f"Verified the first {len(prior_applied) + len(prior_landed)} patches "
            f"on preparation base {queue_base}.",
            flush=True,
        )

    with P.Scratch(engine_repo, args.to, args.tmp) as target:
        first_applied, first_landed, first_conflicts = P.apply_series(target.dir, queue[:position])
        if first_conflicts:
            target.keep = True
            P.report(queue_base, args.to, first_applied, first_landed, first_conflicts)
            raise SystemExit("A patch before 0017 conflicts on current nxnative main")

        before = git(P, "rev-parse", "HEAD", cwd=target.dir).stdout.strip()
        replay = git(P, "-c", "user.name=patches.py", "-c", "user.email=patches@localhost", "-c", "commit.gpgsign=false", "cherry-pick", "--no-edit", pr_sha, cwd=target.dir, check=False)
        steam_applied = []
        steam_landed = []
        if replay.returncode:
            unmerged = git(P, "ls-files", "-u", cwd=target.dir, check=False).stdout.strip()
            clean = (
                git(P, "diff", "--cached", "--quiet", cwd=target.dir, check=False).returncode == 0
                and git(P, "diff", "--quiet", cwd=target.dir, check=False).returncode == 0
            )
            if not unmerged and clean:
                git(P, "cherry-pick", "--skip", cwd=target.dir, check=False)
                steam_landed = [steam_patch]
                print("PR #221 is already present after the preceding patches.", flush=True)
            else:
                target.keep = True
                detail = (replay.stdout + replay.stderr).strip()
                paths = git(
                    P, "diff", "--name-only", "--diff-filter=U",
                    cwd=target.dir, check=False,
                ).stdout.split()
                print("PR #221 three-way conflict files: " + ", ".join(paths), flush=True)
                raise SystemExit(
                    "Original PR #221 needs three-way conflict resolution. " + detail[-9000:]
                )
        else:
            after = git(P, "rev-parse", "HEAD", cwd=target.dir).stdout.strip()
            if after != before:
                subject = "Support Steam Controller and shared Mac control mappings"
                body = """Rebase the original seedds/nxnative PR #221 onto the current nxnative tree after the Dante2iOS branch patches. Preserve controller ownership, motion, haptics and shared Mac input preferences.

Upstream-Status: forwarded seedds/nxnative#221
Reason: Provide Steam Controller support and shared Mac controller mappings on the maintained iOS porting base
Issue: seedds/nxnative#221"""
                amended = git(
                    P, "-c", "user.name=patches.py", "-c", "user.email=patches@localhost",
                    "-c", "commit.gpgsign=false", "commit", "--amend",
                    "-m", subject, "-m", body, cwd=target.dir, check=False,
                )
                if amended.returncode:
                    target.keep = True
                    raise SystemExit(
                        "Could not attach patch-queue metadata to the rebased PR #221 commit. "
                        + amended.stderr[-5000:]
                    )
                steam_sha = git(P, "rev-parse", "HEAD", cwd=target.dir).stdout.strip()
                steam_applied = [(steam_patch, steam_sha)]
                print(f"Rebased original PR #221 as {steam_sha}.", flush=True)
            else:
                steam_landed = [steam_patch]

        last_applied, last_landed, last_conflicts = P.apply_series(target.dir, queue[position + 1:])
        if last_conflicts:
            target.keep = True
            combined_applied = first_applied + steam_applied + last_applied
            combined_landed = first_landed + steam_landed + last_landed
            P.report(queue_base, args.to, combined_applied, combined_landed, last_conflicts)
            raise SystemExit("A later NX2Apple patch conflicts after rebasing patch 0017")

        all_applied = first_applied + steam_applied + last_applied
        all_landed = first_landed + steam_landed + last_landed
        P.write_series(root, target.dir, all_applied, all_landed, queue)
        (root / ".upstream-ref").write_text(args.to + chr(10), encoding="utf-8")
        relinked = E.relink(root)

        print(
            f"Rebased queue onto nxnative {args.to}: "
            f"{len(all_applied)} retained patches, {len(all_landed)} already upstream.",
            flush=True,
        )
        print("Retained: " + ", ".join(p.name for p, _ in all_applied), flush=True)
        if all_landed:
            print("Landed upstream: " + ", ".join(p.name for p in all_landed), flush=True)
        if relinked:
            print("Updated upstream links in: " + ", ".join(p.name for p in relinked), flush=True)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"dante_rebase.py: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
