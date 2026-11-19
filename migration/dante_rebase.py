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
QUEUE_BASE = "94a0944755da1a443f42651bf7ee49ab24ed5ee5"
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


def resolve_conflict_markers(path: Path) -> int:
    """Keep both independent sides of the known 0001 iOS game-data additions."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    out: list[str] = []
    i = 0
    count = 0
    while i < len(lines):
        if not lines[i].startswith("<<<<<<<"):
            out.append(lines[i])
            i += 1
            continue
        i += 1
        left: list[str] = []
        while i < len(lines) and not lines[i].startswith("======="):
            left.append(lines[i])
            i += 1
        if i >= len(lines):
            raise RuntimeError(f"Unterminated conflict in {path}")
        i += 1
        right: list[str] = []
        while i < len(lines) and not lines[i].startswith(">>>>>>>"):
            right.append(lines[i])
            i += 1
        if i >= len(lines):
            raise RuntimeError(f"Unterminated conflict in {path}")
        i += 1
        # The two 0001 conflicts are additive: keep the pin's RomFS locator
        # and the patch's external-folder/program-ROMFS additions.
        out.extend(left)
        out.extend(right)
        count += 1
    if count:
        path.write_text("".join(out), encoding="utf-8")
    return count


def resolve_additive_patch(P, worktree: Path, expected: set[str], label: str) -> str:
    unmerged = set(git(P, "diff", "--name-only", "--diff-filter=U", cwd=worktree, check=False).stdout.splitlines())
    if unmerged != expected:
        raise RuntimeError(f"{label} conflict set changed: " + ", ".join(sorted(unmerged)))
    for relative in sorted(expected):
        count = resolve_conflict_markers(worktree / relative)
        if count != 1:
            raise RuntimeError(f"Expected one additive conflict block in {relative}, found {count}")
    staged = git(P, "add", "--", *sorted(expected), cwd=worktree, check=False)
    if staged.returncode:
        raise RuntimeError(f"Could not stage resolved {label} files: " + staged.stderr[-2000:])
    continued = git(
        P, "-c", "user.name=patches.py", "-c", "user.email=patches@localhost",
        "-c", "commit.gpgsign=false", "am", "--continue",
        cwd=worktree, check=False,
    )
    if continued.returncode:
        raise RuntimeError(f"Could not continue resolved {label} patch: " + (continued.stdout + continued.stderr)[-5000:])
    return git(P, "rev-parse", "HEAD", cwd=worktree).stdout.strip()


def resolve_game_data_patch(P, worktree: Path, patch_path: Path) -> str:
    expected = {
        "dm/ios/Sources/DmIOS-Bridging-Header.h",
        "dm/ios/Sources/main.m",
    }
    result = resolve_additive_patch(P, worktree, expected, "0001")
    print(
        "Resolved 0001 by preserving RomFS/shader-map setup and adding the "
        "external RomFS-program directory plus DataBookmark bridging declarations.",
        flush=True,
    )
    return result


def resolve_mac_keymap_patch(P, worktree: Path) -> str:
    expected = {
        "dm/host/tests/Makefile",
        "dm/tools/impact_map.tsv",
    }
    result = resolve_additive_patch(P, worktree, expected, "0003")
    print(
        "Resolved 0003 additively: kept all existing host tests and added "
        "friends/input-map/launcher-contract tests plus both impact-map entries.",
        flush=True,
    )
    return result


def resolve_dm_screen_patch(P, worktree: Path) -> str:
    expected = {"docs/development.md"}
    unmerged = set(git(P, "diff", "--name-only", "--diff-filter=U", cwd=worktree, check=False).stdout.splitlines())
    if unmerged != expected:
        raise RuntimeError("0006 conflict set changed: " + ", ".join(sorted(unmerged)))
    # The patch's documentation blob is based on an older copy of the whole
    # page. Start from our current stage-2 document and add only its DM_SCREEN
    # sentence; this retains all newer upstream sections and the 0001/0003 docs.
    current = git(P, "show", ":2:docs/development.md", cwd=worktree).stdout
    needle = "`DM_FULLSCREEN=1` starts it that way."
    addition = needle + " `DM_SCREEN=<NSScreenNumber>` opens it on that screen instead of the one macOS picks."
    if current.count(needle) != 1:
        raise RuntimeError("Could not find exactly one fullscreen sentence in current docs/development.md")
    if "DM_SCREEN=<NSScreenNumber>" in current:
        raise RuntimeError("DM_SCREEN documentation already exists; refusing to duplicate it")
    resolved = current.replace(needle, addition, 1)
    path = worktree / "docs/development.md"
    path.write_text(resolved, encoding="utf-8")
    staged = git(P, "add", "--", "docs/development.md", cwd=worktree, check=False)
    if staged.returncode:
        raise RuntimeError("Could not stage resolved 0006 docs: " + staged.stderr[-2000:])
    continued = git(
        P, "-c", "user.name=patches.py", "-c", "user.email=patches@localhost",
        "-c", "commit.gpgsign=false", "am", "--continue",
        cwd=worktree, check=False,
    )
    if continued.returncode:
        raise RuntimeError("Could not continue resolved 0006 patch: " + (continued.stdout + continued.stderr)[-5000:])
    result = git(P, "rev-parse", "HEAD", cwd=worktree).stdout.strip()
    print(
        "Resolved 0006 by retaining the current development guide and adding "
        "only the DM_SCREEN option; upstream documentation changes were preserved.",
        flush=True,
    )
    return result


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True,type=Path)
    ap.add_argument("--to",required=True,help="full nxnative commit SHA resolved from main")
    ap.add_argument("--tmp",type=Path,required=True)
    args=ap.parse_args()

    root=args.repo.resolve()
    args.tmp.mkdir(parents=True,exist_ok=True)
    if not re.fullmatch(r"[0-9a-f]{40}",args.to):
        raise SystemExit("--to must be a full 40-character commit SHA")

    sys.path.insert(0,str(root/"tools"))
    import engine as E
    import patches as P

    nx2apple_pin=E.pin(root)
    if nx2apple_pin!=QUEUE_BASE:
        raise SystemExit(f"NX2Apple .upstream-ref changed: expected {QUEUE_BASE}, found {nx2apple_pin}")
    queue=P.load(root)
    positions=[i for i,p in enumerate(queue) if p.file==PATCH_NAME]
    if len(positions)!=1:
        raise SystemExit(f"Expected exactly one {PATCH_NAME} in patches/series")
    steam_position=positions[0]

    engine_repo=E.scratch_root(root)
    E.fetch(engine_repo,QUEUE_BASE)
    E.fetch(engine_repo,args.to)
    upstream_url=os.environ.get("NX2APPLE_ENGINE_URL") or E.UPSTREAM_URL
    shallow=git(P,"rev-parse","--is-shallow-repository",cwd=engine_repo).stdout.strip()
    if shallow=="true":
        deepened=git(P,"fetch","--quiet","--no-tags","--unshallow",upstream_url,args.to,cwd=engine_repo,check=False)
        if deepened.returncode:
            detail=(deepened.stdout+deepened.stderr).strip()
            raise SystemExit("Could not fetch full nxnative history needed by patch preimages. "+detail[-5000:])
    if git(P,"rev-parse","--is-shallow-repository",cwd=engine_repo).stdout.strip()!="false":
        raise SystemExit("nxnative object database is still shallow")
    if git(P,"merge-base","--is-ancestor",QUEUE_BASE,args.to,cwd=engine_repo,check=False).returncode:
        raise SystemExit(f"NX2Apple source pin {QUEUE_BASE} is not an ancestor of current nxnative main {args.to}")
    print(f"Fetched complete nxnative history: {QUEUE_BASE} -> {args.to}.",flush=True)

    # Reconstruct the queue on its actual NX2Apple pin. This pin is critical:
    # patch 0017's context was prepared on top of patches 0001-0016 from here;
    # replaying on a later intermediate nxnative commit changes its preimages.
    prepared=[]
    already_landed=[]
    with P.Scratch(engine_repo,QUEUE_BASE,args.tmp) as source:
        for index,patch in enumerate(queue):
            before=git(P,"rev-parse","HEAD",cwd=source.dir).stdout.strip()
            if index==steam_position:
                replay=git(P,"-c","user.name=patches.py","-c","user.email=patches@localhost",
                           "-c","commit.gpgsign=false","-c","core.autocrlf=false",
                           "am","--no-3way","--quiet",str(patch.path),cwd=source.dir,check=False)
                if replay.returncode:
                    source.keep=True
                    git(P,"am","--abort",cwd=source.dir,check=False)
                    detail=(replay.stdout+replay.stderr).strip()
                    raise SystemExit("Custom Steam patch 0017 does not apply on the official pin after patches 0001-0016. "
                                     +detail[-9000:])
            else:
                applied,landed,conflicts=P.apply_series(source.dir,[patch])
                if conflicts and patch.file == "0001-ios-game-data-folder.patch":
                    try:
                        resolved_head = resolve_game_data_patch(P, source.dir, patch.path)
                    except Exception as exc:
                        source.keep=True
                        P.report(QUEUE_BASE,QUEUE_BASE,applied,landed,conflicts)
                        raise SystemExit(f"Could not resolve the two known 0001 iOS game-data hunks: {exc}")
                    applied=[(patch,resolved_head)]
                    landed=[]
                    conflicts=[]
                elif conflicts and patch.file == "0003-mac-keymap.patch":
                    try:
                        resolved_head = resolve_mac_keymap_patch(P, source.dir)
                    except Exception as exc:
                        source.keep=True
                        P.report(QUEUE_BASE,QUEUE_BASE,applied,landed,conflicts)
                        raise SystemExit(f"Could not resolve the two additive 0003 Mac key-map hunks: {exc}")
                    applied=[(patch,resolved_head)]
                    landed=[]
                    conflicts=[]
                elif conflicts and patch.file == "0006-front-mac-dm-screen.patch":
                    try:
                        resolved_head = resolve_dm_screen_patch(P, source.dir)
                    except Exception as exc:
                        source.keep=True
                        P.report(QUEUE_BASE,QUEUE_BASE,applied,landed,conflicts)
                        raise SystemExit(f"Could not resolve the additive 0006 DM_SCREEN documentation change: {exc}")
                    applied=[(patch,resolved_head)]
                    landed=[]
                    conflicts=[]
                elif conflicts:
                    source.keep=True
                    P.report(QUEUE_BASE,QUEUE_BASE,applied,landed,conflicts)
                    raise SystemExit(f"Patch {patch.file} cannot be reconstructed from the official NX2Apple pin")
                if landed:
                    already_landed.append(patch)
                    continue
                if len(applied)!=1:
                    raise SystemExit(f"Unexpected source replay result for {patch.file}")
            after=git(P,"rev-parse","HEAD",cwd=source.dir).stdout.strip()
            if after==before:
                already_landed.append(patch)
                continue
            source_patch=patch.path
            indexed=args.tmp/f"indexed-{index:03d}-{patch.file}"
            count=indexed_patch(P,source_patch,indexed,before,after,engine_repo)
            if count==0:
                raise SystemExit(f"No diff sections found for {patch.file}")
            prepared.append((patch,P.Patch(indexed)))
            print(f"Prepared {patch.file}: {count} full blob indexes.",flush=True)
    print(f"Reconstructed queue from official pin: {len(prepared)} indexed, {len(already_landed)} already present.",flush=True)

    with P.Scratch(engine_repo,args.to,args.tmp) as target:
        target_applied=[]
        target_landed=[]
        for original,patch_obj in prepared:
            applied,landed,conflicts=P.apply_series(target.dir,[patch_obj])
            if conflicts:
                target.keep=True
                P.report(args.to,args.to,target_applied,target_landed,[(original,msg) for _,msg in conflicts])
                paths=git(P,"diff","--name-only","--diff-filter=U",cwd=target.dir,check=False).stdout.split()
                print("Rebase conflict paths: "+", ".join(paths),flush=True)
                raise SystemExit(f"Patch {original.file} has a real three-way conflict on current nxnative main")
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
        print(f"Rebased full queue onto nxnative {args.to}: {len(target_applied)} retained, {len(all_landed)} already upstream.",flush=True)
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
