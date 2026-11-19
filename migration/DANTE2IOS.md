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

Only `Dante2iOS` receives the migration commit. `SpkIOSzero` and every other branch remain untouched. The bootstrap archives the Spk reference and replaces the active workflows with only Dante2iOS engine validation and manual nxnative-sync workflows. Validation checks the official patch queue, materializes the engine, runs Python tooling tests and compilation/shell checks, and checks the project directory layout. No game packages, decryption keys, RomFS, DLC images or shader cache are committed.

## Follow-on phase

After a validated baseline, advance nxnative with the branch's explicit sync workflow and resolve conflicts against that *current* NX2Apple patch queue. The subsequent DMC2-specific phase starts from the NSP the user already possesses, using profile survey and a separate game build workflow.
