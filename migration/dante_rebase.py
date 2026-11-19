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
import subprocess
import sys
from pathlib import Path


PATCH_NAME = "0017-support-steam-controller-and-shared-mac-control.patch"
QUEUE_BASE = "94a0944755da1a443f42651bf7ee49ab24ed5ee5"
JOYCON_PR_COMMIT = "c7d7bd484d7af2d50a4ed9201cfa22409631cf86"
JOYCON_PR_PARENT = "04811a634b7f9344e882129b0973dd493369dd62"
JOYCON_PR_REF = "refs/dante2ios/pr-1322"
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


def profile_target_key(line: str):
    match = re.match(r'^\$\(B\)/([^: ]+):', line)
    return match.group(1) if match else None


def add_profile_source(command: str) -> str:
    if "../hle_profile.c" in command:
        return command
    ending = "\n" if command.endswith("\n") else ""
    body = command[:-1] if ending else command
    continuation = body.endswith("\\")
    if continuation:
        body = body[:-1].rstrip()
    positions = [
        match.start()
        for match in re.finditer(r"\s(?:-framework\s+|-l[A-Za-z0-9_]+)", body)
    ]
    if positions:
        at = min(positions)
        body = body[:at] + " ../hle_profile.c" + body[at:]
    else:
        body += " ../hle_profile.c"
    if continuation:
        body += " \\"
    return body + ending


def merge_profile_test_makefile(current_text: str, postimage_text: str) -> str:
    current = current_text.splitlines(keepends=True)
    postimage = postimage_text.splitlines(keepends=True)
    target_indices: dict[str, list[int]] = {}
    for index, line in enumerate(current):
        key = profile_target_key(line)
        if key:
            target_indices.setdefault(key, []).append(index)

    # Carry only the runtime-profile prerequisites introduced by 0009 onto
    # target rules which already exist at the declared NX2Apple source pin.
    # Later upstream-only test targets are intentionally not copied backwards.
    for line in postimage:
        key = profile_target_key(line)
        if not key or ("../hle_profile.c" not in line and "../hle_profile.h" not in line):
            continue
        for index in target_indices.get(key, []):
            old = current[index]
            if "../hle_profile.c" in old:
                continue
            if "| $(B)" in old:
                current[index] = old.replace(
                    "| $(B)", "../hle_profile.c ../hle_profile.h | $(B)"
                )
            else:
                current[index] = old.rstrip("\n") + " ../hle_profile.c ../hle_profile.h\n"

    # Link hle_profile.c into existing test executables which now reference
    # dm_profile(). Match by Make target, retaining the old pin's own flags,
    # source list, ordering and any branch-local test additions.
    for index, line in enumerate(postimage):
        if not (
            line.startswith("\t")
            and "-o $@" in line
            and "../hle_profile.c" in line
        ):
            continue
        key = None
        for previous in range(index - 1, -1, -1):
            key = profile_target_key(postimage[previous])
            if key:
                break
        if not key or key not in target_indices:
            continue
        command_index = None
        for target_index in target_indices[key]:
            for candidate in range(target_index + 1, min(len(current), target_index + 16)):
                if candidate > target_index + 1 and profile_target_key(current[candidate]):
                    break
                if current[candidate].startswith("\t") and "-o $@" in current[candidate]:
                    command_index = candidate
                    break
            if command_index is not None:
                break
        if command_index is not None:
            current[command_index] = add_profile_source(current[command_index])

    # The memory tests use one shared dependency variable.
    memory_deps = next(
        (
            line for line in postimage
            if line.startswith("MEM_DEPS =") and "../hle_profile.c" in line
        ),
        None,
    )
    if memory_deps:
        for index, line in enumerate(current):
            if line.startswith("MEM_DEPS =") and "../hle_profile.c" not in line:
                current[index] = line.rstrip("\n") + " ../hle_profile.c ../hle_profile.h\n"
                break

    # Add the runtime-profile regression executable to the existing branch
    # test run list and run recipe, but do not import unrelated newer tests.
    profile_target = "$(B)/t_profile_runtime"
    for index, line in enumerate(current):
        if (
            line.startswith("run:")
            and "$(B)/t_launcher_contract" in line
            and profile_target not in line
        ):
            current[index] = line.rstrip("\n") + " " + profile_target + "\n"
            break

    run_command = 'TMPDIR="$(abspath $(B))" $(B)/t_profile_runtime'
    if not any(line.strip() == run_command for line in current):
        for index, line in enumerate(current):
            if line.strip() == "$(B)/t_shared_font":
                current.insert(index + 1, "\t" + run_command + "\n")
                break

    if not any("$(B)/t_profile_runtime:" in line for line in current):
        start = next(
            (index for index, line in enumerate(postimage)
             if line.startswith("# runtime-profile test:")),
            None,
        )
        if start is None:
            raise RuntimeError("The 0009 runtime-profile test target is absent from the patch postimage")
        current.append("\n")
        current.extend(postimage[start:])

    merged = "".join(current)
    if merged.count("$(B)/t_profile_runtime:") != 1:
        raise RuntimeError("Expected exactly one t_profile_runtime target after resolving 0009")
    if sum(
        line.startswith("run:") and profile_target in line
        for line in merged.splitlines()
    ) != 1:
        raise RuntimeError("Expected t_profile_runtime in exactly one run prerequisite")
    if sum(line.strip() == run_command for line in merged.splitlines()) != 2:
        raise RuntimeError("Expected t_profile_runtime in the run recipe and profile-runtime target")
    if any(line.startswith(("<<<<<<<", "=======", ">>>>>>>")) for line in merged.splitlines()):
        raise RuntimeError("Conflict markers remain in the resolved host test Makefile")
    return merged


def resolve_runtime_profile_patch(P, worktree: Path) -> str:
    expected = {
        "dm/host/hle_fs.c",
        "dm/host/tests/Makefile",
    }
    unmerged = set(
        git(P, "diff", "--name-only", "--diff-filter=U", cwd=worktree, check=False)
        .stdout.splitlines()
    )
    if unmerged != expected:
        raise RuntimeError(
            "0009 conflict set changed: " + ", ".join(sorted(unmerged))
        )

    # hle_fs.c has a small semantic change: make the existing single-user save
    # path read IDs from the runtime profile. Do not import account-user,
    # per-user-save or multi-program RomFS code from the newer postimage blob.
    fs = git(P, "show", ":2:dm/host/hle_fs.c", cwd=worktree).stdout
    if fs.count("DM_GAME_PROGRAM_ID") != 3 or fs.count("DM_GAME_ID") != 2:
        raise RuntimeError("Unexpected static game-ID references in the 0009 hle_fs preimage")
    fs = fs.replace("DM_GAME_PROGRAM_ID", "dm_profile()->program_id")
    fs = fs.replace("DM_GAME_ID", "dm_profile()->id")
    fs_path = worktree / "dm/host/hle_fs.c"
    fs_path.write_text(fs, encoding="utf-8")

    # Rebuild the conflicted Makefile from stage 2 (the official old pin plus
    # the preceding branch patches), carrying only the 0009 profile link edits
    # and its own test target from stage 3.
    make_current = git(P, "show", ":2:dm/host/tests/Makefile", cwd=worktree).stdout
    make_postimage = git(P, "show", ":3:dm/host/tests/Makefile", cwd=worktree).stdout
    make_merged = merge_profile_test_makefile(make_current, make_postimage)
    make_path = worktree / "dm/host/tests/Makefile"
    make_path.write_text(make_merged, encoding="utf-8")

    staged = git(
        P, "add", "--", "dm/host/hle_fs.c", "dm/host/tests/Makefile",
        cwd=worktree, check=False,
    )
    if staged.returncode:
        raise RuntimeError("Could not stage the resolved 0009 files: " + staged.stderr[-3000:])

    continued = git(
        P, "-c", "user.name=patches.py", "-c", "user.email=patches@localhost",
        "-c", "commit.gpgsign=false", "am", "--continue",
        cwd=worktree, check=False,
    )
    if continued.returncode:
        raise RuntimeError(
            "Could not continue the resolved 0009 patch: "
            + (continued.stdout + continued.stderr)[-7000:]
        )
    result = git(P, "rev-parse", "HEAD", cwd=worktree).stdout.strip()
    print(
        "Resolved 0009 by switching only the five game-ID references to the "
        "runtime profile and linking hle_profile.c into the existing profile-dependent "
        "tests; the pin's save/filesystem structure and branch-local test list were retained.",
        flush=True,
    )
    return result


def resolve_ios_quit_patch(P, worktree: Path) -> str:
    expected = {"dm/ios/Sources/front_ios.m"}
    unmerged = set(
        git(P, "diff", "--name-only", "--diff-filter=U", cwd=worktree, check=False)
        .stdout.splitlines()
    )
    if unmerged != expected:
        raise RuntimeError(
            "0012 conflict set changed: " + ", ".join(sorted(unmerged))
        )

    # Stage 3 is the patch's newer whole-file postimage. It contains newer
    # upstream audio/screen edits unrelated to #421, so transplant only the
    # appended quit implementation and its required imports/prototypes onto
    # our current stage-2 front end.
    current = git(P, "show", ":2:dm/ios/Sources/front_ios.m", cwd=worktree).stdout
    postimage = git(P, "show", ":3:dm/ios/Sources/front_ios.m", cwd=worktree).stdout
    tag = "// ---- Quit to the launcher (LNPANDY/NX2Apple#421) ----"
    if current.count(tag) != 0 or postimage.count(tag) != 1:
        raise RuntimeError("Could not isolate the unique quit-to-launcher implementation block")
    quit_block = postimage[postimage.index(tag):]
    if "dm_movie_active(0)" in postimage or "dm_movie_active(1)" in postimage:
        # Those calls are from later upstream movie-lifecycle work, not this
        # quit feature. They live before the quit block and are not imported.
        pass

    def replace_once(text: str, old: str, new: str, label: str) -> str:
        if text.count(old) != 1:
            raise RuntimeError(f"Expected exactly one {label} insertion point")
        return text.replace(old, new, 1)

    # Headers needed by the new implementation. home_quit.h is present at the
    # declared nxnative pin; quit_prompt.h is added by this same patch.
    current = replace_once(
        current,
        '#import <AVFAudio/AVFAudio.h>\n',
        '#import <AVFAudio/AVFAudio.h>\n#import <GameController/GameController.h>\n',
        "GameController import",
    )
    current = replace_once(
        current,
        '#include "save_sync.h"\n',
        '#include "save_sync.h"\n#include "home_quit.h"\n',
        "home_quit include",
    )
    current = replace_once(
        current,
        '#import "CloudSaves.h"\n',
        '#import "CloudSaves.h"\n#import "quit_prompt.h"\n',
        "quit prompt import",
    )
    current = replace_once(
        current,
        'void dm_gamepad_active(void);\n',
        'void dm_gamepad_active(void);\nvoid dm_gamepad_pads_read(void);\nstatic void quit_close(void);\n',
        "gamepad-read and quit-close prototypes",
    )

    # The foreground-resign event closes any active prompt before inputs are
    # reset. Do not import the unrelated newer dm_movie_active hooks.
    current = replace_once(
        current,
        'case 0: dm_gamepad_reset(); dm_focus_set(2); break;',
        'case 0: quit_close(); dm_gamepad_reset(); dm_focus_set(2); break;',
        "focus-resign quit close",
    )
    if "dm_movie_active(" in current:
        raise RuntimeError("Unexpected movie-lifecycle dependency in current front_ios.m")
    resolved = current.rstrip() + "\n\n" + quit_block.rstrip() + "\n"
    if resolved.count(tag) != 1:
        raise RuntimeError("Quit implementation block was not appended exactly once")
    if "static void quit_close(void)" not in resolved or "void dm_gamepad_pads_read(void);" not in resolved:
        raise RuntimeError("Quit implementation prototypes are incomplete")
    if "int front_ios_quit_blocks_input(void)" not in resolved or "void *dm_quit_menu(void)" not in resolved:
        raise RuntimeError("Quit implementation exports are incomplete")
    if "dm_movie_active(" in resolved:
        raise RuntimeError("Unrelated movie-lifecycle call leaked into the quit resolution")
    if any(line.startswith(("<<<<<<<", "=======", ">>>>>>>")) for line in resolved.splitlines()):
        raise RuntimeError("Conflict markers remain in resolved front_ios.m")

    path=worktree/"dm/ios/Sources/front_ios.m"
    path.write_text(resolved,encoding="utf-8")
    staged=git(P,"add","--","dm/ios/Sources/front_ios.m",cwd=worktree,check=False)
    if staged.returncode:
        raise RuntimeError("Could not stage resolved 0012 front_ios.m: "+staged.stderr[-3000:])
    continued=git(
        P,"-c","user.name=patches.py","-c","user.email=patches@localhost",
        "-c","commit.gpgsign=false","am","--continue",
        cwd=worktree,check=False,
    )
    if continued.returncode:
        raise RuntimeError(
            "Could not continue resolved 0012 patch: "
            +(continued.stdout+continued.stderr)[-7000:]
        )
    result=git(P,"rev-parse","HEAD",cwd=worktree).stdout.strip()
    print(
        "Resolved 0012 by keeping the official-pin front_ios.m, adding the "
        "quit prompt imports/prototypes and focus-close hook, and transplanting "
        "only the #421 quit implementation (no newer audio/screen/movie changes).",
        flush=True,
    )
    return result


def resolve_nsp_experimental_builder_patch(P, worktree: Path) -> str:
    expected = {"scripts/build_ipa_from_nsp.py"}
    unmerged = set(
        git(P, "diff", "--name-only", "--diff-filter=U", cwd=worktree, check=False)
        .stdout.splitlines()
    )
    if unmerged != expected:
        raise RuntimeError(
            "0013 conflict set changed: " + ", ".join(sorted(unmerged))
        )

    current = git(P, "show", ":2:scripts/build_ipa_from_nsp.py", cwd=worktree).stdout
    postimage = git(P, "show", ":3:scripts/build_ipa_from_nsp.py", cwd=worktree).stdout

    def replace_once(text: str, old: str, new: str, label: str) -> str:
        if text.count(old) != 1:
            raise RuntimeError(f"Expected exactly one {label} integration point")
        return text.replace(old, new, 1)

    # The experimental helpers are the dedicated nxbuild block in the patch's
    # postimage. Do not replace the whole script: that blob also contains later
    # NUP multi-program, profile-source-cache, capture and renderer changes.
    helper_start = postimage.index("# ---- The experimental builder (nxbuild) ----")
    helper_end = postimage.index("\n\n# ---- NSP identification ----", helper_start)
    experimental_helpers = postimage[helper_start:helper_end].rstrip()
    if "def nxb_tool(" not in experimental_helpers or "def nxb_extract(" not in experimental_helpers or "def nxb_split(" not in experimental_helpers:
        raise RuntimeError("The nxbuild helper block is incomplete")

    # nxb_extract rejects NSZ, merged NSPs and XCIs before invoking nxbuild.
    # These small parsers are part of the experimental-builder patch; keep the
    # existing nx_extract path and all of its package validation unchanged.
    parser_start = postimage.index("def pfs0_names(")
    parser_end = postimage.index("def is_package(path):", parser_start)
    package_helpers = postimage[parser_start:parser_end].rstrip()
    if "def package_names(" not in package_helpers:
        raise RuntimeError("The PFS0/HFS0 package-name helpers are incomplete")

    # A visible opt-in note in the script header; with the switch off, no path
    # or behavior changes and the existing builder remains the default.
    header = next(
        (line for line in current.splitlines(keepends=True)
         if line.startswith("# The console shows one line per stage")),
        None,
    )
    if header is None:
        raise RuntimeError("Could not find the script's progress/header description")
    current = replace_once(
        current, header,
        header + "# DM_EXPERIMENTAL_BUILDER=1 with NXB_BIN enables nxbuild extraction and shader splitting where supported; other cases use the standard tools.\n",
        "experimental-builder header",
    )

    current = replace_once(
        current,
        "# ---- NSP identification ----",
        experimental_helpers + "\n\n# ---- NSP identification ----",
        "experimental-builder helper insertion",
    )
    current = replace_once(
        current,
        "def is_package(path):",
        package_helpers + "\n\n def is_package(path):".replace("\n ", "\n"),
        "PFS0/HFS0 package parser insertion",
    )

    # Keep the standard extraction exactly as before unless nxb_extract
    # validates a complete output and its title ID; on unsupported/failure/
    # mismatched output it removes the partial folder and runs nx_extract.
    old_extract = "    run([nx, keys, base, upd or '-', tmp, '--romfs-image'] + extract_flags(app), log)\n"
    new_extract = (
        "    if not nxb_extract(keys, base, upd, tmp, logs, name, app, marker):\n"
        "        run([nx, keys, base, upd or '-', tmp, '--romfs-image'] + extract_flags(app), log)\n"
    )
    current = replace_once(current, old_extract, new_extract, "NSP extraction fallback")

    # A NUP's version extraction has its own reuse stamp and aoc images; never
    # hand control to nxbuild unless its entire output passes all checks.
    old_nup_sig = "def extract_nup(ex, name, k, base, app, n):"
    current = replace_once(
        current, old_nup_sig,
        "def extract_nup(ex, name, k, base, app, n, marker=None):",
        "NUP extraction signature",
    )
    nup_stage = "        PROG.stage(f'unpack {name}', poll=poll, unit='B', total=n.tree_bytes(pack_nup.romfs_of(k, base)), est=True)\n"
    current = replace_once(
        current, nup_stage,
        nup_stage
        + "        if nxb_extract_nup(ex, name, k, base, app, n, marker):\n"
        + "            PROG.end(amount((dst / 'RomFS.img').stat().st_size, 'B')); return dst\n",
        "NUP experimental extraction",
    )

    # nxb-extract writes NUP DLC images alongside version images. Reuse those
    # files rather than extracting the same content a second time.
    old_aoc = (
        "    if fam.get('nup'):\n"
        "        PROG.stage('unpack DLC', step='unpacking')\n"
        "        try: pack_nup.pack_dlc(fam['nup'], app, {tid: k for tid, _, k in fam['dlc']}, work / 'aoc', say=lambda s: None)\n"
    )
    new_aoc = (
        "    if fam.get('nup'):\n"
        "        PROG.stage('unpack DLC', step='unpacking')\n"
        "        if fam['nup'].path in _nxb_nups and all((work / 'aoc' / f'{tid - app - 0x1000}.img').is_file() for tid, _, _ in fam['dlc']):\n"
        "            want = {f'{tid - app - 0x1000}.img' for tid, _, _ in fam['dlc']}\n"
        "            for f in (work / 'aoc').iterdir():\n"
        "                if f.name not in want: rmtree(f)\n"
        "            PROG.end(f'{len(fam[\"dlc\"])} DLC'); return work / 'aoc'\n"
        "        try: pack_nup.pack_dlc(fam['nup'], app, {tid: k for tid, _, k in fam['dlc']}, work / 'aoc', say=lambda s: None)\n"
    )
    current = replace_once(current, old_aoc, new_aoc, "NUP DLC reuse")

    # The split only goes through nxb-split for an ordinary registered profile
    # with plain extracted RomFS images and no DLC, captures, NROs or decoder.
    old_split = (
        "    run([py, repo / 'dm/gfx/tools/shader_split.py', ','.join(map(str, roms)), ','.join(map(str, mains)), tmp / 'pkg'] + [tmp / 'tables' / n for n in names + ('pso_pairs.tsv',)] + ([','.join(map(str, dlc_roms))] if dlc_roms else []),\n"
        "        logs / 'shader_split.log', env=env, on_line=counted)\n"
        "    text = (logs / 'shader_split.log').read_text(errors='replace')\n"
    )
    new_split = (
        "    # The experimental builder takes a registered profile's split of the game files alone; DLC, run-time captures, NROs and a game decoder stay with shader_split.py.\n"
        "    captured = env.get('DM_NRO_DIR') or any(env.get(s) or next((Path(r).parent / f).glob(p), None) for r in roms for s, f, p in\n"
        "                                             (('DM_GLSLC_CAPTURE', 'glslc_capture', '*.glslc'), ('DM_UE_SHADERS', 'ue_shaders', '*.ushaderbytecode')))\n"
        "    plain = not (provisional or oodle or dlc_roms or captured)\n"
        "    if not plain and os.environ.get('DM_EXPERIMENTAL_BUILDER') == '1':\n"
        "        nxb_note('shader split: a provisional or derived profile, DLC, run-time captures or a game decoder is not supported yet, the standard builder runs it')\n"
        "    text = nxb_split(roms, mains, tmp, names, logs, g) if plain else None\n"
        "    if text is None:\n"
        "        run([py, repo / 'dm/gfx/tools/shader_split.py', ','.join(map(str, roms)), ','.join(map(str, mains)), tmp / 'pkg'] + [tmp / 'tables' / n for n in names + ('pso_pairs.tsv',)] + ([','.join(map(str, dlc_roms))] if dlc_roms else []),\n"
        "            logs / 'shader_split.log', env=env, on_line=counted)\n"
        "        text = (logs / 'shader_split.log').read_text(errors='replace')\n"
    )
    current = replace_once(current, old_split, new_split, "shader-split fallback")

    # Supply the registered RomFS marker to the NUP path too, so the same
    # validation prevents an incomplete image from being accepted by nxbuild.
    old_bottom = "dirs[ver] = extract_nup(ex, ver, u or b, b, app, fam['nup']) if nup else"
    current = replace_once(
        current, old_bottom,
        "dirs[ver] = extract_nup(ex, ver, u or b, b, app, fam['nup'], g.get('romfs_marker')) if nup else",
        "NUP RomFS marker",
    )

    if current.count("def nxb_extract(") != 1 or current.count("def nxb_extract_nup(") != 1 or current.count("def nxb_split(") != 1:
        raise RuntimeError("The integrated experimental-builder helpers are not unique")
    if current.count("if not nxb_extract(keys, base, upd, tmp, logs, name, app, marker):") != 1:
        raise RuntimeError("The standard extraction fallback is not wired exactly once")
    if current.count("text = nxb_split(roms, mains, tmp, names, logs, g) if plain else None") != 1:
        raise RuntimeError("The standard shader-split fallback is not wired exactly once")

    path = worktree / "scripts/build_ipa_from_nsp.py"
    path.write_text(current, encoding="utf-8")
    pycheck = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True, text=True,
    )
    if pycheck.returncode:
        raise RuntimeError("The integrated NSP builder does not compile: " + pycheck.stderr[-5000:])
    staged = git(P, "add", "--", "scripts/build_ipa_from_nsp.py", cwd=worktree, check=False)
    if staged.returncode:
        raise RuntimeError("Could not stage resolved 0013 script: " + staged.stderr[-3000:])
    continued = git(
        P, "-c", "user.name=patches.py", "-c", "user.email=patches@localhost",
        "-c", "commit.gpgsign=false", "am", "--continue",
        cwd=worktree, check=False,
    )
    if continued.returncode:
        raise RuntimeError(
            "Could not continue resolved 0013 patch: "
            + (continued.stdout + continued.stderr)[-7000:]
        )
    result = git(P, "rev-parse", "HEAD", cwd=worktree).stdout.strip()
    print(
        "Resolved 0013 by keeping the pin's existing NSP/NUP pipeline and "
        "adding guarded nxbuild extraction/shader-split adapters with output "
        "checks and fallback; only its two added helpers/tests and required "
        "integration points were retained.",
        flush=True,
    )
    return result


def joycon_replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def resolve_joycon_pr_1322(P, worktree: Path) -> str:
    """Resolve the three Joy-Con PR overlaps while retaining the current Dante frontend."""
    expected = {
        "dm/host/Makefile",
        "dm/host/front_mac.m",
        "dm/host/hle_hid.c",
    }
    unmerged = set(
        git(P, "diff", "--name-only", "--diff-filter=U", cwd=worktree, check=False)
        .stdout.splitlines()
    )
    if unmerged != expected:
        raise RuntimeError(
            "Joy-Con PR #1322 conflict set changed: " + ", ".join(sorted(unmerged))
        )

    # The current NX2Apple pin builds host objects with compiler-generated
    # dependency files (-MMD/-MP). PR #1322's Makefile hunk targets an older
    # monolithic build; keep stage 2 unchanged rather than importing that
    # obsolete rule. Its new headers are included by the compiler depfiles.
    makefile = git(P, "show", ":2:dm/host/Makefile", cwd=worktree).stdout

    front = git(P, "show", ":2:dm/host/front_mac.m", cwd=worktree).stdout
    pr_front = git(P, "show", ":3:dm/host/front_mac.m", cwd=worktree).stdout

    # New unified Joy-Con Bluetooth transport supersedes the old JC1 HID path.
    # Keep the newer Dante key-map, cursor, Switch 2 rumble and Pro-motion code.
    front = joycon_replace_once(
        front, '#include "pad_jc1_mac.h"\n', "",
        "old JC1 header removal",
    )
    include_anchor = "static void merge_rumble_to(void (*sink)(const dm_haptic_state *));\n"
    front = joycon_replace_once(
        front, include_anchor,
        include_anchor + '#include "pad_joycon_mac.h"\n',
        "new Joy-Con header insertion",
    )
    front = joycon_replace_once(
        front,
        "static int pad_gc_unread(GCController *c) { return hidpad_gc_unread(c) || jc1_gc_unread(c); }",
        "static int pad_gc_unread(GCController *c) { return hidpad_gc_unread(c) || (g_joycon_split && joycon_is_gc_controller(c)); }",
        "GameController HID unread filter",
    )
    front = joycon_replace_once(
        front,
        "// GameController's controllers that the host reads from their HID reports instead, so they stay unread here: identical pads (pad_hid_mac.h) and original Joy-Cons (pad_jc1_mac.h)",
        "// GameController controllers read from raw HID stay unread: identical pads and Joy-Con controllers handled by pad_joycon_mac.h",
        "HID unread comment",
    )

    # Import only the PR's Joy-Con filter and haptics routing helpers, not its
    # older front-end globals or Switch 2 rumble implementation.
    helper_start = pr_front.index("static int gc_pad_used(GCController *c) {")
    helper_end = pr_front.index(
        "// DM_PAD_MERGE: whether a controller still plays player 1",
        helper_start,
    )
    joycon_helpers = pr_front[helper_start:helper_end].rstrip()
    merge_comment = "// DM_PAD_MERGE: whether a controller still plays player 1 (gone: one just removed, not counted), a GameController one or a raw HID pad (pad_hid_mac.h)\n"
    front = joycon_replace_once(
        front, merge_comment, joycon_helpers + "\n" + merge_comment,
        "Joy-Con filter/haptics helper insertion",
    )

    # DM_PAD_MERGE must count raw Joy-Cons after the old g_jc1_pads list is gone.
    ours_merge_start = front.index("static int merge_pads_left(GCController *gone) {")
    ours_merge_end = front.index("\n// Called at start and on every connect / disconnect", ours_merge_start)
    pr_merge_start = pr_front.index("static int merge_pads_left(GCController *gone) {")
    pr_merge_end = pr_front.index("\n// Called at start and on every connect / disconnect", pr_merge_start)
    front = front[:ours_merge_start] + pr_front[pr_merge_start:pr_merge_end] + front[ours_merge_end:]

    # Replace the controller-connect routine's JC1-specific branches with the
    # PR Joy-Con model while retaining the current Pro-motion callback name.
    ours_changed_start = front.index("static void pads_changed(GCController *gone) {")
    ours_changed_end = front.index("\n// Display sleep:", ours_changed_start)
    pr_changed_start = pr_front.index("static void pads_changed(GCController *gone) {")
    pr_changed_end = pr_front.index("\n// Display sleep:", pr_changed_start)
    changed = pr_front[pr_changed_start:pr_changed_end]
    changed = changed.replace("hidpad_gc_unread(", "pad_gc_unread(")
    changed = changed.replace("pro_players_changed(", "pads_motion_changed(")
    front = front[:ours_changed_start] + changed + front[ours_changed_end:]

    # Replace only the old JC1 transport callbacks with the original PR's
    # Joy-Con attach/read/pair/split code. Keep the Dante Home-quit UI unchanged.
    old_joy_start = front.index(
        "// Original Joy-Cons read from their HID reports (pad_jc1_mac.h):"
    )
    old_joy_end = front.index("// Quit with the Home button", old_joy_start)
    new_joy_start = pr_front.index("// Bluetooth Joy-Cons (pad_joycon_mac.h):")
    new_joy_end = pr_front.index("// Quit with the Home button", new_joy_start)
    joycon_block = pr_front[new_joy_start:new_joy_end].rstrip()
    front = front[:old_joy_start] + joycon_block + "\n" + front[old_joy_end:]

    # Clear the gamepad state and the correct Joy-Con side on focus loss;
    # reread the unified HID driver when focus returns.
    front = joycon_replace_once(
        front,
        "    for (jc1_pad *d = g_jc1_pads; d; d = d->next) { int p = jc1pad_player(d); if (p >= 0) { dm_pad_set_player(p, 0, 0, 0, 0, 0); dm_joy_set(p, 0, 0, 0, 0); dm_joy_set(p, 1, 0, 0, 0); } }",
        """    for (joycon_pad *d = g_joycons; d; d = d->next) {
        joycon_pad *pri = joycon_pad_primary(d);
        int p = pad_slot_of(&g_slots, pri);
        if (p >= 0) { dm_pad_set_player(p, 0, 0, 0, 0, 0); dm_joy_set(p, joycon_side(d->st.pid), 0, 0, 0); }
    }""",
        "pads_release Joy-Con state clear",
    )
    front = joycon_replace_once(
        front,
        "    if (g_merge) { for (GCController *c in GCController.controllers) if (c.extendedGamepad) pad_read(c.extendedGamepad); }",
        "    if (g_merge) { for (GCController *c in GCController.controllers) if (gc_pad_used(c)) pad_read(c.extendedGamepad); }",
        "pads_reread merged GameController filter",
    )
    front = joycon_replace_once(
        front,
        "    for (jc1_pad *d = g_jc1_pads; d; d = d->next) jc1pad_read(d);",
        "    for (joycon_pad *d = g_joycons; d; d = d->next) joycon_read(d);",
        "pads_reread Joy-Con loop",
    )

    # The new driver is gated by g_input_on; it has no separate JC1 active switch.
    front = joycon_replace_once(
        front,
        "    dm_switch2_active(0); dm_jc1_active(0);\n",
        """    dm_switch2_active(0);
    for (joycon_pad *d = g_joycons; d; d = d->next) {
        d->motion = (pro_motion){0};
        joycon_pad *pri = joycon_pad_primary(d);
        int p = g_merge ? 0 : pad_slot_of(&g_slots, pri);
        if (p >= 0) {
            dm_motion_clear_hid(p);
            if (!g_merge) dm_motion_clear_joy(p, joycon_side(d->st.pid));
        }
    }
""",
        "input_release Joy-Con motion clear",
    )
    front = joycon_replace_once(
        front,
        "    dm_switch2_active(1); dm_jc1_active(1);\n",
        "    dm_switch2_active(1);\n",
        "input_resume Joy-Con reactivation removal",
    )

    # The Home and controller prompts read buttons from the same Joy-Con state.
    front = joycon_replace_once(
        front,
        "    for (jc1_pad *d = g_jc1_pads; d; d = d->next) { if (jc1_pad_home(d)) *home = 1; jc1_pad_ab(d, a, b); }   // original Joy-Cons read from HID (pad_jc1_mac.h)",
        """    for (joycon_pad *d = g_joycons; d; d = d->next) {
        if (d->st.home) *home = 1;
        uint64_t m = d->partner ? d->st.joy_buttons : d->st.buttons;
        if (m & DM_BTN_A) *a = 1;
        if (m & DM_BTN_B) *b = 1;
    }""",
        "Home prompt Joy-Con buttons",
    )
    front = joycon_replace_once(
        front,
        "    for (GCController *c in GCController.controllers) {\n        GCExtendedGamepad *g = c.extendedGamepad; if (!g) continue;",
        "    for (GCController *c in GCController.controllers) {\n        if (!gc_pad_used(c)) continue;\n        GCExtendedGamepad *g = c.extendedGamepad; if (!g) continue;",
        "Home prompt GameController duplicate filter",
    )
    front = joycon_replace_once(
        front,
        "    for (jc1_pad *d = g_jc1_pads; d; d = d->next) jc1_pad_ab(d, a, b);             // original Joy-Cons read from HID (pad_jc1_mac.h)",
        """    for (joycon_pad *d = g_joycons; d; d = d->next) {
        uint64_t m = d->partner ? d->st.joy_buttons : d->st.buttons;
        if (m & DM_BTN_A) *a = 1;
        if (m & DM_BTN_B) *b = 1;
    }""",
        "controller prompt Joy-Con buttons",
    )
    front = joycon_replace_once(
        front,
        "    for (GCController *c in GCController.controllers) if (c.extendedGamepad && !pad_gc_unread(c) && pad_slot_of(&g_slots, (__bridge const void *)c) < 0) n++;\n    for (jc1_pad *d = g_jc1_pads; d; d = d->next) if (pad_slot_of(&g_slots, d) < 0) n++;",
        "    for (GCController *c in GCController.controllers) if (gc_pad_used(c) && !pad_gc_unread(c) && pad_slot_of(&g_slots, (__bridge const void *)c) < 0) n++;",
        "controller prompt waiting Joy-Con count",
    )

    # Start the IOHID Joy-Con manager before the initial controller scan.
    front = joycon_replace_once(
        front,
        "    hq_start();\n    pads_changed(nil);",
        "    hq_start();\n    joycon_start();\n    pads_changed(nil);",
        "Joy-Con manager startup order",
    )
    front = joycon_replace_once(
        front,
        "    dm_jc1_start(g_merge);\n",
        "",
        "old JC1 manager startup removal",
    )
    front = joycon_replace_once(
        front,
        "                GCController *c = n.object; int conn = n.name == GCControllerDidConnectNotification;\n",
        "                GCController *c = n.object; int conn = n.name == GCControllerDidConnectNotification;\n                if (g_joycon_split && joycon_is_gc_controller(c)) return;\n",
        "GameController duplicate Joy-Con observer filter",
    )

    legacy = (
        "pad_jc1_mac.h", "jc1_pad", "jc1pad_", "g_jc1_pads",
        "dm_jc1_", "jc1_gc_unread", "g_jc1_",
    )
    for symbol in legacy:
        if symbol in front:
            raise RuntimeError(f"Old JC1 transport reference remains in front_mac.m: {symbol}")
    for symbol in (
        '#include "pad_joycon_mac.h"', "static int gc_pad_used",
        "static void joycon_haptics_sync", "static void joycon_read",
        "joycon_start();", "pads_motion_changed(gone)",
        "g_held_fn = 0", "g_shift_fn",
    ):
        if symbol not in front:
            raise RuntimeError(f"Joy-Con integration is missing required current-front-end code: {symbol}")

    # Stage 2's modern object-based Makefile is intentionally retained.
    makefile = git(P, "show", ":2:dm/host/Makefile", cwd=worktree).stdout
    if "-MMD -MP" not in makefile:
        raise RuntimeError("Expected current host Makefile's generated dependency-file model")

    # hle_hid.c: add the re-pair reset while retaining current side-report
    # bookkeeping and the live six-axis history/sampling implementation.
    hid = git(P, "show", ":2:dm/host/hle_hid.c", cwd=worktree).stdout
    if "static _Thread_local live_hist src" not in hid or "answer_tick(&g_hwm_states" not in hid:
        raise RuntimeError("Refusing to replace the current live six-axis history implementation")
    old_attach = """    if (sides == 3 || !sides) atomic_store(&g_joy_paired[p], sides == 3);
    atomic_fetch_and(&g_joy_reported[p], sides);   // a Joy-Con taken away has reported nothing yet when it comes back
    if (atomic_exchange(&g_joy_sides[p], sides) != sides && !sides) for (int s = 0; s < 2; s++) { atomic_store(&g_joy_btn[p][s], 0); atomic_store(&g_joy_axes[p][s], 0); }
    styles_sync();"""
    new_attach = """    if (sides == 3 || !sides) atomic_store(&g_joy_paired[p], sides == 3);
    atomic_fetch_and(&g_joy_reported[p], sides);   // a Joy-Con taken away has reported nothing yet when it comes back
    uint32_t old = atomic_exchange(&g_joy_sides[p], sides);
    if (sides == 3 && old != 0) atomic_fetch_and(&g_single_mask, ~(1u << p));
    if (old != sides && !sides) for (int s = 0; s < 2; s++) { atomic_store(&g_joy_btn[p][s], 0); atomic_store(&g_joy_axes[p][s], 0); }
    styles_sync();"""
    hid = joycon_replace_once(hid, old_attach, new_attach, "dm_joy_attach single-assignment reset")

    old_six = """    for (int i = 0; i < n; i++) six_at(&out[i], samp - i, &src, shakes);
    return n;"""
    new_six = """    int split = ((1u << (h & 0xff)) & (STYLE_JOYDUAL | STYLE_JOYLEFT | STYLE_JOYRIGHT)) != 0;
    for (int i = 0; i < n; i++) {
        six_at(&out[i], samp - i, &src, shakes);
        // Super Mario Party rejects a Joy-Con sample when an acceleration component is exactly zero.
        if (split) for (int k = 0; k < 3; k++) if (out[i].acc[k] == 0.0f) out[i].acc[k] = 1e-6f;
    }
    return n;"""
    hid = joycon_replace_once(hid, old_six, new_six, "six-axis zero-acceleration workaround")

    front_path = worktree / "dm/host/front_mac.m"
    hid_path = worktree / "dm/host/hle_hid.c"
    front_path.write_text(front, encoding="utf-8")
    hid_path.write_text(hid, encoding="utf-8")

    staged = git(
        P, "add", "--",
        "dm/host/Makefile", "dm/host/front_mac.m", "dm/host/hle_hid.c",
        cwd=worktree, check=False,
    )
    if staged.returncode:
        raise RuntimeError("Could not stage resolved Joy-Con PR #1322 overlaps: " + staged.stderr[-4000:])

    continued = git(
        P, "-c", "user.name=patches.py", "-c", "user.email=patches@localhost",
        "-c", "commit.gpgsign=false", "cherry-pick", "--continue",
        cwd=worktree, check=False,
    )
    if continued.returncode:
        raise RuntimeError(
            "Could not continue original Joy-Con PR #1322 after the targeted merge: "
            + (continued.stdout + continued.stderr)[-9000:]
        )

    print(
        "Resolved original PR #1322: retained the modern object-based Makefile, "
        "replaced the old JC1 Bluetooth transport with the unified Joy-Con driver, "
        "kept current Pro-motion/Switch 2/key-map logic, and preserved the live "
        "six-axis history while adding the Joy-Con re-pair and zero-acceleration fixes.",
        flush=True,
    )
    return git(P, "rev-parse", "HEAD", cwd=worktree).stdout.strip()


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

    # Patch 0014 is a branch-local subset of original Joy-Con PR #1322.
    # Its mail-diff Makefile preimage belongs to an intermediate queue tree;
    # fetch the original commit so Git can use the real parent and file blobs.
    if git(P,"merge-base","--is-ancestor",JOYCON_PR_PARENT,QUEUE_BASE,cwd=engine_repo,check=False).returncode:
        raise SystemExit(f"Joy-Con PR #1322 parent {JOYCON_PR_PARENT} is not an ancestor of NX2Apple pin {QUEUE_BASE}")
    pr_fetch=git(P,"fetch","--quiet","--no-tags","https://github.com/seedds/nxnative.git",
                 f"+refs/pull/1322/head:{JOYCON_PR_REF}",cwd=engine_repo,check=False)
    if pr_fetch.returncode:
        detail=(pr_fetch.stdout+pr_fetch.stderr).strip()
        raise SystemExit("Could not fetch original seedds/nxnative PR #1322. "+detail[-5000:])
    joycon_sha=git(P,"rev-parse",JOYCON_PR_REF,cwd=engine_repo).stdout.strip()
    if joycon_sha!=JOYCON_PR_COMMIT:
        raise SystemExit(f"Joy-Con PR #1322 head changed: expected {JOYCON_PR_COMMIT}, found {joycon_sha}")
    if git(P,"rev-parse",f"{joycon_sha}^",cwd=engine_repo).stdout.strip()!=JOYCON_PR_PARENT:
        raise SystemExit("Joy-Con PR #1322 parent changed; refusing different patch ancestry")
    print(f"Verified original Joy-Con PR #1322 commit {joycon_sha} and parent {JOYCON_PR_PARENT}.",flush=True)

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
            elif patch.file == "0014-mac-split-a-joy-con-pair-into-two-sideways-contr.patch":
                # Replay the actual upstream PR commit, not the custom mail
                # patch with stale intermediate preimages. Preserve the scope
                # of branch patch 0014 by restoring the two PR files it omitted.
                replay=git(P,"-c","user.name=patches.py","-c","user.email=patches@localhost",
                           "-c","commit.gpgsign=false","cherry-pick","--no-edit",
                           JOYCON_PR_COMMIT,cwd=source.dir,check=False)
                if replay.returncode:
                    unmerged=git(P,"ls-files","-u",cwd=source.dir,check=False).stdout.strip()
                    clean=(git(P,"diff","--cached","--quiet",cwd=source.dir,check=False).returncode==0
                           and git(P,"diff","--quiet",cwd=source.dir,check=False).returncode==0)
                    if not unmerged and clean:
                        git(P,"cherry-pick","--skip",cwd=source.dir,check=False)
                        already_landed.append(patch)
                        print("Joy-Con PR #1322 is already present after patches 0001-0013.",flush=True)
                        continue
                    try:
                        resolve_joycon_pr_1322(P, source.dir)
                    except Exception as exc:
                        source.keep=True
                        paths=git(P,"diff","--name-only","--diff-filter=U",cwd=source.dir,check=False).stdout.split()
                        raise SystemExit(
                            "Could not resolve the three original Joy-Con PR #1322 integration overlaps. "
                            + "files: " + ", ".join(paths) + "; " + str(exc)
                        )
                restore=git(P,"restore","--source",before,"--staged","--worktree",
                            "--","dm/host/Makefile","docs/env_switches.tsv",
                            cwd=source.dir,check=False)
                if restore.returncode:
                    source.keep=True
                    raise SystemExit("Could not restore the two files excluded from branch patch 0014. "+restore.stderr[-3000:])
                amend_body="""Rebase the original seedds/nxnative Joy-Con PR #1322 into the Dante2iOS branch patch queue.

Upstream-Status: forwarded seedds/nxnative#1322
Reason: Add native Mac Joy-Con split HID handling, motion and rumble to the existing controller backend
Issue: seedds/nxnative#1322"""
                amended=git(P,"-c","user.name=patches.py","-c","user.email=patches@localhost",
                            "-c","commit.gpgsign=false","commit","--amend",
                            "-m","Mac: split a Joy-Con pair into two sideways controllers",
                            "-m",amend_body,cwd=source.dir,check=False)
                if amended.returncode:
                    source.keep=True
                    raise SystemExit("Could not attach patch metadata to rebased Joy-Con PR #1322. "+amended.stderr[-5000:])
                generated=args.tmp/"0014-original-joycon-pr-1322.patch"
                formatted=git(P,"format-patch","--binary","--zero-commit","--no-signature",
                              "--no-numbered","--stdout","-1","HEAD",cwd=source.dir,binary=True)
                generated.write_bytes(formatted.stdout)
                source_patch=generated
                conflicts=[]
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
                elif conflicts and patch.file == "0009-runtime-profile.patch":
                    try:
                        resolved_head = resolve_runtime_profile_patch(P, source.dir)
                    except Exception as exc:
                        source.keep=True
                        P.report(QUEUE_BASE,QUEUE_BASE,applied,landed,conflicts)
                        raise SystemExit(f"Could not resolve the 0009 runtime-profile source/test integration: {exc}")
                    applied=[(patch,resolved_head)]
                    landed=[]
                    conflicts=[]
                elif conflicts and patch.file == "0012-ios-quit-a-game-from-the-in-game-menu-or-by-hold.patch":
                    try:
                        resolved_head = resolve_ios_quit_patch(P, source.dir)
                    except Exception as exc:
                        source.keep=True
                        P.report(QUEUE_BASE,QUEUE_BASE,applied,landed,conflicts)
                        raise SystemExit(f"Could not resolve the 0012 iOS quit-to-launcher integration: {exc}")
                    applied=[(patch,resolved_head)]
                    landed=[]
                    conflicts=[]
                elif conflicts and patch.file == "0013-nsp-script-hand-the-extraction-and-the-shader-sp.patch":
                    try:
                        resolved_head = resolve_nsp_experimental_builder_patch(P, source.dir)
                    except Exception as exc:
                        source.keep=True
                        P.report(QUEUE_BASE,QUEUE_BASE,applied,landed,conflicts)
                        raise SystemExit(f"Could not resolve the 0013 experimental nxbuild extraction/shader adapter: {exc}")
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
