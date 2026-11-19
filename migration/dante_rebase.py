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
    """Write full blob indexes from the exact old/new commit trees."""
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    out: list[str] = []
    i = 0
    count = 0
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
        old_entry = tree_entry(P, old_commit, old_path, repo)
        new_entry = tree_entry(P, new_commit, new_path, repo)
        if old_entry is None and new_entry is None:
            raise RuntimeError(f"Patch path is absent from both trees: {old_path}")
        old_blob = old_entry[1] if old_entry else ZERO
        new_blob = new_entry[1] if new_entry else ZERO
        suffix = " " + old_entry[0] if old_entry and new_entry and old_entry[0] == new_entry[0] else ""
        index_line = f"index {old_blob}..{new_blob}{suffix}\n"
        section = [item for item in section if not item.startswith("index ")]
        place = next((n for n,item in enumerate(section) if item.startswith("--- ") or item.startswith("@@")),len(section))
        section.insert(place,index_line)
        out.append(line)
        out.extend(section)
        count += 1
        i = end
    destination.write_text("".join(out), encoding="utf-8")
    return count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--to", required=True, help="full nxnative commit SHA resolved from main")
    ap.add_argument("--tmp", type=Path, required=True)
    args = ap.parse_args()

    root = args.repo.resolve()
    args.tmp.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch(r"[0-9a-f]{40}", args.to):
        raise SystemExit("--to must be a full 40-character commit SHA")

    sys.path.insert(0, str(root / "tools"))
    import engine as E
    import patches as P

    nx2apple_pin = E.pin(root)
    if nx2apple_pin != "94a0944755da1a443f42651bf7ee49ab24ed5ee5":
        raise SystemExit(f"Unexpected NX2Apple source pin {nx2apple_pin}")
    queue_base = QUEUE_BASE
    queue = P.load(root)

    engine_repo = E.scratch_root(root)
    E.fetch(engine_repo, nx2apple_pin)
    E.fetch(engine_repo, args.to)
    E.fetch(engine_repo, queue_base)

    upstream_url = os.environ.get("NX2APPLE_ENGINE_URL") or E.UPSTREAM_URL
    shallow = git(P, "rev-parse", "--is-shallow-repository", cwd=engine_repo).stdout.strip()
    if shallow == "true":
        deepened = git(P,"fetch","--quiet","--no-tags","--unshallow",upstream_url,args.to,cwd=engine_repo,check=False)
        if deepened.returncode:
            detail=(deepened.stdout+deepened.stderr).strip()
            raise SystemExit("Could not fetch complete nxnative history. "+detail[-5000:])
    shallow = git(P, "rev-parse", "--is-shallow-repository", cwd=engine_repo).stdout.strip()
    if shallow != "false":
        raise SystemExit("nxnative object database is still shallow")
    print(f"Fetched complete nxnative history through {args.to}.",flush=True)

    if git(P,"merge-base","--is-ancestor",queue_base,args.to,cwd=engine_repo,check=False).returncode:
        raise SystemExit(f"Queue preparation base {queue_base} is not an ancestor of target {args.to}")

    # Recreate the exact intended series on its preparation base. Generate
    # full old/new blob IDs for every patch, including patches after 0017.
    prepared=[]
    already_landed=[]
    with P.Scratch(engine_repo,queue_base,args.tmp) as source:
        for index,patch in enumerate(queue):
            before=git(P,"rev-parse","HEAD",cwd=source.dir).stdout.strip()
            if patch.name == "support-steam-controller-and-shared-mac-control":
                replay=git(P,"-c","user.name=patches.py","-c","user.email=patches@localhost",
                           "-c","commit.gpgsign=false","-c","core.autocrlf=false",
                           "am","--no-3way","--quiet",str(patch.path),cwd=source.dir,check=False)
                if replay.returncode:
                    source.keep=True
                    git(P,"am","--abort",cwd=source.dir,check=False)
                    detail=(replay.stdout+replay.stderr).strip()
                    raise SystemExit("Custom Steam patch 0017 does not apply to the post-0016 source tree. "+detail[-9000:])
            else:
                applied,landed,conflicts=P.apply_series(source.dir,[patch])
                if conflicts:
                    source.keep=True
                    P.report(queue_base,queue_base,applied,landed,conflicts)
                    raise SystemExit(f"Patch {patch.file} cannot be reconstructed on preparation base {queue_base}")
                if landed:
                    already_landed.append(patch)
                    continue
                if len(applied)!=1:
                    raise SystemExit(f"Unexpected source replay result for {patch.file}")

            after=git(P,"rev-parse","HEAD",cwd=source.dir).stdout.strip()
            if after==before:
                already_landed.append(patch)
                continue
            temp=args.tmp/f"indexed-{index:03d}-{patch.file}"
            count=indexed_patch(P,patch.path,temp,before,after,engine_repo)
            if count==0:
                raise SystemExit(f"No diff sections found in {patch.file}")
            prepared.append((patch,P.Patch(temp)))
            print(f"Prepared {patch.file}: {count} full blob indexes.",flush=True)
    print(f"Reconstructed queue: {len(prepared)} patches indexed; {len(already_landed)} already present.",flush=True)

    # Reapply each patch on current main. Every three-way ancestor is available
    # in the full object database, independent of earlier rebased postimages.
    with P.Scratch(engine_repo,args.to,args.tmp) as target:
        target_applied=[]
        target_landed=[]
        for original,patch_obj in prepared:
            applied,landed,conflicts=P.apply_series(target.dir,[patch_obj])
            if conflicts:
                target.keep=True
                mapped=[(original,detail) for _,detail in conflicts]
                P.report(args.to,args.to,target_applied,target_landed,mapped)
                paths=git(P,"diff","--name-only","--diff-filter=U",cwd=target.dir,check=False).stdout.split()
                print("Rebase conflict paths: "+", ".join(paths),flush=True)
                raise SystemExit(f"Patch {original.file} has a three-way conflict on current nxnative main")
            if applied:
                target_applied.append((original,applied[0][1]))
            elif landed:
                target_landed.append(original)
            else:
                raise SystemExit(f"Unexpected target replay result for {original.file}")
            print(f"Replayed {original.file}: "+("applied" if applied else "already upstream"),flush=True)

        all_landed=already_landed+target_landed
        P.write_series(root,target.dir,target_applied,all_landed,queue)
        (root/".upstream-ref").write_text(args.to+chr(10),encoding="utf-8")
        relinked=E.relink(root)
        print(
            f"Rebased full queue onto nxnative {args.to}: "
            f"{len(target_applied)} retained patches, {len(all_landed)} already upstream.",
            flush=True,
        )
        print("Retained: "+", ".join(p.name for p,_ in target_applied),flush=True)
        if all_landed:
            print("Landed upstream: "+", ".join(p.name for p in all_landed),flush=True)
        if relinked:
            print("Updated upstream links in: "+", ".join(relinked),flush=True)
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"dante_rebase.py: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
