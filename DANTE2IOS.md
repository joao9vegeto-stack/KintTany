# Dante2iOS — NX2Apple / nxnative migration

This branch is the **reusable native iOS porting base** for the later Devil May Cry 2 work. This phase does **not** extract or compile a game, produce an IPA, or guess a DMC2-specific profile.

## Authoritative sources and reproducibility

- `NX2APPLE_REF` records the exact `LNPANDY/NX2Apple` main commit obtained by the bootstrap workflow.
- `.upstream-ref` is copied **unchanged** from that NX2Apple commit. It is the exact nxnative engine revision against which the official `patches/series` was authored.
- The entire NX2Apple patch queue, including its current versions of `0001`–`0017` and later patches, is copied without replacing old patches, altering preimage hashes, or dropping changes.
- `python3 tools/engine.py check` and `sync` validate/materialize the pinned engine in the ignored `engine/` tree; the engine itself is not a committed duplicate.
- Updating **nxnative beyond the verified NX2Apple pin** is a separate explicit action using `.github/workflows/dante-sync-upstream.yml`. A successful bootstrap does not claim the pin equals whichever upstream main commit happens to be newest.

## Why the older bootstrap was retired

The original Dante2iOS migration assumed an older nxnative pin (`94a0944755da1a443f42651bf7ee49ab24ed5ee5`) and copied older local patches on top of whatever NX2Apple main it downloaded. As NX2Apple main advanced, the patch ancestry and source contents diverged: its `.upstream-ref` changed, its queue grew beyond `0017`, and some local patch copies contained obsolete whole-file preimages. This caused a long succession of failed rebases; simply refreshing old index hashes did not correct semantic drift. The new bootstrap resolves this by making the contemporary NX2Apple snapshot, its pin and its full queue **one atomic versioned baseline**. A separate bump attempts new nxnative main only after a valid baseline exists.

## Preserved work from SpkIOSzero

`legacy/spkioszero/` is a non-active, readable reference containing:

- Colab notebooks and Drive source/prepare/recover scripts.
- Original Actions workflow and preparation / finalization scripts.
- iOS launcher, build, crash-diagnostic overrides.
- Sparking! ZERO profile seed for identifying its game-specific logic.

Those resources do not run in the Dante2iOS app or modify generic runtime behavior. Their fixed game identifiers, profile hashes, asset paths, shader handling and DLC assumptions must not be applied to DMC2. Reusable ideas include verified/restartable Drive transfer, strict package handoff manifests, staged RomFS/AOC layouts, shader-map validation and branch-isolated CI.

## Branch isolation and validation

Only `Dante2iOS` receives the migration commit. `SpkIOSzero` and every other branch remain untouched. The bootstrap archives the Spk reference and uses Dante2iOS engine validation and manual nxnative-sync workflows; it also retains the five upstream workflow files `build-mac-app.yml`, `sync-upstream.yml`, `build-qt.yml`, `tests.yml` and `release-notes.yml` that upstream's Mac and Qt regression tests inspect. Their original push triggers do not target `Dante2iOS`. When testing upstream release manifests on the fork, the regression suite sets `GITHUB_REPOSITORY=LNPANDY/NX2Apple` so the upstream test fixture expects the upstream release URL; this does not change the fork's actual release destination. Validation checks the official patch queue, materializes the engine, runs Python tooling tests and compilation/shell checks, and checks the project directory layout. No game packages, decryption keys, RomFS, DLC images or shader cache are committed.

## Follow-on phase

After a validated baseline, advance nxnative with the branch's explicit sync workflow and resolve conflicts against that *current* NX2Apple patch queue. The subsequent DMC2-specific phase starts from the NSP the user already possesses, using profile survey and a separate game build workflow.

The native NX2Apple pre-push hook is **not disabled**. The bootstrap installs the same `capstone` and `unicorn` wheel versions required by its Qt test suite before the final push, and executes those tests explicitly. The upstream release-fixture repository name is set only in the test environment, never in the fork's Git remote.

The official triage-script regression suite also runs before commit, alongside the Qt and tools tests; its workflow fixtures are present as pristine upstream copies. Only `Dante2iOS` receives this branch update, while the upstream workflows' automatic push branches remain `main`.

The bootstrap runner label is `xcode-27` (macOS 27, Xcode 27), matching NX2Apple's current launcher API availability: `GCControllerHomeButtonSettingsManager` is not in the Xcode 26 SDK on `macos-26`. This selects the required Apple SDK instead of weakening or replacing upstream Swift code.

## Xcode 27.1 SwiftUI compatibility

The exact upstream NX2Apple source snapshot remains the baseline. Xcode 27.1's SDK does not yet expose `GeometryProxy.reservedRegions(kind:)` or `ArrangementView` used in upstream's divided-display views. The Dante bootstrap applies a deterministic, fail-closed compatibility script: five `GeometryProxy` call sites use a named empty-region adapter, leaving UIKit native region APIs untouched, and the unreachable `ArrangementView` tabletop branch falls back to the existing expanded/portrait layout. No nxnative engine, patch queue, game profile, or regular layout is changed. The script fails if upstream changes these call sites unexpectedly. The bootstrap compiles the Swift shell before the costly inherited pre-push test suites; those suites are not skipped.


## GitHub Actions workflow permission boundary

Run #82 (44587274425) passed the engine checks, source/Python tests, 1,400 native macOS launcher tests (50 skipped, zero failures), and native iOS shell tests. Its push was rejected only because the runner token cannot update `.github/workflows/build-mac-app.yml`. The bootstrap now stages no changes under `.github/workflows/` or `migration/` for its final push; it preserves both directories from the authenticated branch HEAD. Upstream workflow fixtures remain in the working tree during the full hook, so the tests are unchanged. The five reference workflows are added to this branch in a separate authenticated repository commit before running the bootstrap, avoiding the runner's workflow write restriction. The final source commit does not retrigger the bootstrap because neither its workflow nor its migration input files change.