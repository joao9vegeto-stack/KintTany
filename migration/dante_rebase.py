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
import re
import sys
from pathlib import Path


PATCH_NAME = "0017-support-steam-controller-and-shared-mac-control.patch"
ZERO = "0" * 40


def git(P, *args: str, cwd: Path, check: bool = True):
    return P.git(*args, cwd=cwd, check=check)


def tree_entry(P, commit: str, path: str, cwd: Path):
    result = git(P, "ls-tree", commit, "--", path, cwd=cwd, check=False)
    rows = result.stdout.splitlines()
    if not rows:
        return None
    fields = rows[0].split(None, 3)
    if len(fields) < 3 or fields[1] != "blob":
        return None
    return fields[0], fields[2]


def indexed_patch(P, source: Path, destination: Path, old_commit: str, new_commit: str, repo: Path):
    """Replace every patch index with blob IDs from the exact old/new trees."""
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    i = 0
    indexed = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("diff --git "):
            out.append(line)
            i += 1
            continue

        end = i + 1
        while end < len(lines) and not lines[end].startswith("diff --git "):
            end += 1
        section = lines[i + 1:end]
        match = re.match(r"diff --git a/(.+) b/(.+)$", line.rstrip("\r\n"))
        if not match:
            raise RuntimeError("Unparseable diff header: " + line.rstrip())
        old_path, new_path = match.group(1), match.group(2)
        if old_path != new_path:
            raise RuntimeError(f"Rename/copy patch section needs manual handling: {old_path} -> {new_path}")

        old_entry = tree_entry(P, old_commit, old_path, repo)
        new_entry = tree_entry(P, new_commit, new_path, repo)
        if old_entry is None and new_entry is None:
            raise RuntimeError(f"Patch path is absent from both materialized trees: {old_path}")
        old_blob = old_entry[1] if old_entry else ZERO
        new_blob = new_entry[1] if new_entry else ZERO
        suffix = ""
        if old_entry and new_entry and old_entry[0] == new_entry[0]:
            suffix = " " + old_entry[0]
        index_line = f"index {old_blob}..{new_blob}{suffix}\n"

        # Remove stale or abbreviated indexes from the handcrafted patch and
        # insert the verified full object IDs after mode metadata, before ---.
        section = [item for item in section if not item.startswith("index ")]
        insert_at = next(
            (n for n, item in enumerate(section)
             if item.startswith("--- ") or item.startswith("@@")),
            len(section),
        )
        section.insert(insert_at, index_line)
        out.append(line)
        out.extend(section)
        indexed += 1
        i = end

    destination.write_text("".join(out), encoding="utf-8")
    return indexed


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

    old_pin = E.pin(root)
    if old_pin != "94a0944755da1a443f42651bf7ee49ab24ed5ee5":
        raise SystemExit(f"Unexpected starting pin {old_pin}; expected the migration's recorded base")
    queue = P.load(root)
    positions = [i for i, patch in enumerate(queue) if patch.file == PATCH_NAME]
    if len(positions) != 1:
        raise SystemExit(f"Expected exactly one {PATCH_NAME} in patches/series")
    position = positions[0]
    steam_patch = queue[position]

    engine_repo = E.scratch_root(root)
    E.fetch(engine_repo, old_pin)
    E.fetch(engine_repo, args.to)

    anchor = f"refs/dante2ios/rebase/{args.to[:12]}/steam-0017-postimage"
    target_success = False

    # Materialize the patch's exact before/after blobs on its declared base.
    with P.Scratch(engine_repo, old_pin, args.tmp) as base:
        prior_applied, prior_landed, prior_conflicts = P.apply_series(base.dir, queue[:position])
        if prior_conflicts:
            P.report(old_pin, old_pin, prior_applied, prior_landed, prior_conflicts)
            raise SystemExit("The first sixteen patches no longer reproduce the declared old base")
        before = git(P, "rev-parse", "HEAD", cwd=base.dir).stdout.strip()

        replay = git(
            P, "-c", "user.name=patches.py",
            "-c", "user.email=patches@localhost",
            "-c", "commit.gpgsign=false",
            "-c", "core.autocrlf=false",
            "am", "--no-3way", "--quiet", str(steam_patch.path),
            cwd=base.dir, check=False,
        )
        if replay.returncode:
            git(P, "am", "--abort", cwd=base.dir, check=False)
            detail = (replay.stdout + "\n" + replay.stderr).strip()
            raise SystemExit(
                "Patch 0017 does not apply to its declared old base after patches 0001-0016.\n"
                + detail[-9000:]
            )
        after = git(P, "rev-parse", "HEAD", cwd=base.dir).stdout.strip()
        if after == before:
            raise SystemExit("Patch 0017 produced no commit on its declared old base")

        indexed = args.tmp / "0017-with-verified-blob-indexes.patch"
        count = indexed_patch(P, steam_patch.path, indexed, before, after, engine_repo)
        if count == 0:
            raise SystemExit("No diff sections were indexed; refusing an ungrounded three-way rebase")
        temp_patch = P.Patch(indexed)

        # Keep the generated postimage commit reachable in the shared object
        # database while the target worktree performs git am -3.
        git(P, "update-ref", anchor, after, cwd=engine_repo)
        print(f"Materialized {count} verified blob indexes for patch 0017.", flush=True)
        print(f"Old patch base: {before}", flush=True)
        print(f"Old patch postimage: {after}", flush=True)

        # Replay the entire queue on current main. Patch 0017 now has the real
        # preimage and postimage IDs, so Git can merge changed upstream files.
        with P.Scratch(engine_repo, args.to, args.tmp) as target:
            first_applied, first_landed, first_conflicts = P.apply_series(target.dir, queue[:position])
            if first_conflicts:
                P.report(old_pin, args.to, first_applied, first_landed, first_conflicts)
                raise SystemExit("A patch before 0017 conflicts on current nxnative main")

            steam_applied, steam_landed, steam_conflicts = P.apply_series(target.dir, [temp_patch])
            if steam_conflicts:
                P.report(old_pin, args.to, first_applied + steam_applied,
                         first_landed + steam_landed, steam_conflicts)
                raise SystemExit("Steam/controller patch 0017 has a genuine three-way conflict on current nxnative main")

            # Substitute the repository patch object for the temporary indexed
            # copy so write_series updates patches/0017... in the checkout.
            steam_commits = [(steam_patch, commit) for _, commit in steam_applied]
            steam_landed_original = [steam_patch for _ in steam_landed]

            last_applied, last_landed, last_conflicts = P.apply_series(target.dir, queue[position + 1:])
            if last_conflicts:
                combined_applied = first_applied + steam_commits + last_applied
                combined_landed = first_landed + steam_landed_original + last_landed
                P.report(old_pin, args.to, combined_applied, combined_landed, last_conflicts)
                raise SystemExit("A later NX2Apple patch conflicts after rebasing patch 0017")

            all_applied = first_applied + steam_commits + last_applied
            all_landed = first_landed + steam_landed_original + last_landed
            P.write_series(root, target.dir, all_applied, all_landed, queue)
            (root / ".upstream-ref").write_text(args.to + "\n", encoding="utf-8")
            relinked = E.relink(root)
            target_success = True

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

    if target_success:
        git(P, "update-ref", "-d", anchor, cwd=engine_repo, check=False)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"dante_rebase.py: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
