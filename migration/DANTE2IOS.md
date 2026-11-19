# Dante2iOS — reusable NX2Apple / nxnative base

This branch is being converted into a maintained, reusable native iOS porting base. This migration does **not** extract Devil May Cry 2, create a DMC2 profile, compile game shaders, or build an IPA.

## Exact source references

- NX2Apple frontend and patch-queue snapshot: the bootstrap resolves the current `LNPANDY/NX2Apple` `main` HEAD at run time and records the exact 40-character commit in `NX2APPLE_REF`.
- nxnative target: the workflow resolves the current `seedds/nxnative` `main` HEAD immediately before the rebase and records the full 40-character SHA in `.upstream-ref`.
- The Steam Controller patch `0017` is branch-specific and follows the post-`0016` queue. The original queue's declared base is NX2Apple pin `94a0944755da1a443f42651bf7ee49ab24ed5ee5`. The bootstrap rebuilds the queue on the official pin using complete nxnative history, computes full before/after blob IDs for every patch, and reapplies each patch to current nxnative `main` with a three-way merge. Source-tree conflicts have explicit, scope-limited resolutions: `0001` keeps the original RomFS/shader-map locator while adding the external-folder bookmark and `DM_ROMFS_PROGRAMS`; `0003` keeps existing test targets and adds the friends/key-map/launcher tests and impact-map rows; `0006` keeps the current development guide and adds only its `DM_SCREEN` sentence; `0009` changes only the existing static game-ID references in `hle_fs.c` to runtime-profile lookups and adds the profile source/test dependencies to the pin's existing test targets. The latter deliberately retains the old pin's single-user save/filesystem structure instead of copying unrelated newer account-save and multi-program RomFS code from the patch's later preimage. Patch `0017` remains the branch's context-rebased custom patch. The queue and `.upstream-ref` are written only after the full series rebases, then stock NX2Apple `check` and `sync` validate the result.
- The Joy-Con split patch `0014` is kept as a branch-specific rebase with full blob indexes for the post-`0013` tree.
- Upstream engine is materialized by `python3 tools/engine.py sync` into ignored `engine/`. Its source of truth is `.upstream-ref` plus `patches/series`, not a committed copy of the engine.

## Why this migration is necessary

SpkIOSzero was created from an older nxnative snapshot. Comparing the original Spk engine tree against its ancestor showed that the core builder, profile guesser and NSO rewriter matched upstream at the time; much of the later improvement was already upstream development. The latest nxnative is therefore the correct reusable base rather than freezing that older engine.

NX2Apple separates the native engine from the launcher/frontends. It maintains a pinned nxnative commit and an ordered, reviewable patch queue. Its repository contains the current iOS shell, per-game library, macOS/Windows frontends, NSP build integration, thin-IPA handling and supporting tests.

## Rebase of the iOS game-data patch

The official NX2Apple sync was blocked at patch `0001-ios-game-data-folder.patch` on nxnative `3443d482...` (NX2Apple issue #1199). The conflict was in `dm/ios/Sources/main.m` and `DmIOS-Bridging-Header.h`.

The branch migration replaces that patch with a rebase onto the newer nxnative iOS entry point. The resulting patch keeps the upstream runtime game profile, multi-program handling and RomFS identity checks, while layering the NX2Apple data bookmark and per-game data-folder behavior on top. It is validated by replaying the full patch series with `tools/engine.py bump`, then running the patch-queue and tooling tests. The patch is not considered migrated unless this validation passes.

## What is carried forward from SpkIOSzero

The SpkIOSzero-specific implementation is preserved under `legacy/spkioszero/` as a non-active reference:

- Colab notebooks and Drive source/prepare/recover scripts.
- The isolated workflow and Actions handoff/validation scripts.
- The macOS finalizer and diagnostics.
- The old iOS entry-point and build-script overrides.

These scripts deliberately remain inactive because they hard-code Sparking! ZERO's Title ID, main Build ID and SHA-256, profile, allocator observations, NVN/Unreal/Oodle shader path, package/DLC counts and app metadata. Those assumptions are not generic and must not be applied to a different title. Reusable concepts include checksummed/resumable Drive transfers, strict package manifests, external RomFS/AOC handoff, shader-map validation and isolated branch workflows. The newer NX2Apple pipeline is the active base for those capabilities.

## Branch safety

- Only `Dante2iOS` is updated by this migration.
- `SpkIOSzero` remains the source reference and is not modified.
- The old SpkIOSzero workflow is archived and is not active.
- The active workflows are branch-guarded to `Dante2iOS`.
- The migration runs patch checks, NX2Apple tooling tests, Python compilation and shell syntax checks. It does not process any game package.
- No NSP, XCI, `prod.keys`, RomFS, AOC or shader cache is committed.

## Next phase (not part of this migration)

After the generic base is synchronized and validated, a separate task can feed Devil May Cry 2's own NSP into nxnative's survey/profile workflow. No DMC2-specific code is introduced in this base update.
