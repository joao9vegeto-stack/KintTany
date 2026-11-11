# Link2iOS — Present Snapshots + Metal Encode Thread Audit

Date: 2026-11-11
Target: BOTW (01007EF00011E000), iPhone 17 Pro / Apple A19 Pro, iOS 26.5.1
Branch: Link2iOS

## Executive result

The uploaded runtime logs prove that the two requested runtime switches are passed as enabled:
- `DM_PRESENT_SNAP=1`
- `DM_NVN_ENC_THREAD=1`

The logs also prove that the host Metal path reports a dedicated encoding thread and that present snapshots are active. The snapshots implementation reports a ring of two host textures, allowing the game's render texture to be released immediately after each present.

However, one internal profile summary prints `enc_thread 0` while the boot environment prints `DM_NVN_ENC_THREAD=1`. This is a configuration/diagnostic discrepancy, not sufficient evidence that the encode thread is disabled. The same runtime explicitly logs: "Metal encoding runs on its own thread (DM_NVN_ENC_THREAD=0 turns it off)". The implementation state must be confirmed with a runtime trace or a targeted A/B run, not inferred from the profile summary alone.

## Source audit

The Link2iOS branch already contains:
- `scripts/patches/botw-metal4-encode-thread.patch`
- `scripts/optimize_existing_ipa.py`
- `.github/workflows/link2ios-optimize.yml`

The patch modifies only `dm/gfx/nvn/nvn_mtl.m` in the pinned NX2Apple engine. It adds/adjusts Metal 4 timestamp accounting, command-buffer boundary tracking, and GPU idle-gap accounting. It is a host-renderer optimization; it does not recompile BOTW guest modules or alter game assets.

The optimizer:
- applies the reviewed patch to the exact pinned engine;
- rebuilds only the BOTW host framework;
- reuses embedded game modules, RomFS/AOC, shader libraries and pipeline archive;
- preserves the existing 60 FPS profile and checks the generated runtime profile;
- emits a build report and optimized IPA artifact.

The workflow is branch-scoped to `Link2iOS`, uses Xcode 27.2 on `xcode-27`, and cancels an in-progress run for the same branch.

## Runtime evidence from supplied logs

Observed:
- `DM_FPS_TARGET=60`
- `DM_FPS_HOLD=on`
- `DM_PRESENT_SNAP=1`
- `DM_NVN_ENC_THREAD=1`
- `present snapshots ... ring of 2 host textures`
- `Metal encoding runs on its own thread`
- the game changes present interval from 1 to 2 and later back to 1.

The present-interval transitions are a separate investigation item. They show the game changing its requested presentation interval; they do not, by themselves, prove that this causes the reported 60-to-30 FPS drops.

## What is not yet proven

The supplied logs are startup/configuration logs, not a frame-time trace. They do not include sustained per-frame CPU encode time, GPU execution time, command-buffer commit gaps, present deadlines, thermal-state transitions, or the exact moments when FPS falls from 60 to 30. Therefore they cannot identify a single bottleneck or justify claiming that the 30 FPS drops are fixed.

The `switches ... enc_thread 0` line must be reconciled against the enabled boot variable. It may be a profile field that does not represent the environment override. Confirm the code path that reads `DM_NVN_ENC_THREAD` and log the final effective value after override resolution.

## Required next verification

1. Add a startup diagnostic that prints the effective encode-thread value after profile defaults and environment overrides are resolved.
2. Verify the present-snapshot ring allocation, acquisition/release, and back-pressure behavior under sustained gameplay.
3. Run controlled A/B captures with snapshots+encode thread both enabled, then each disabled individually. Keep the same game profile, render scale, thermal conditions and scene.
4. Record frame intervals and CPU/GPU/Metal command-buffer timings across the 60-to-30 transition. Distinguish a true 30 FPS cap (one frame every two 60 Hz vsyncs) from a counter/reporting artifact.
5. Inspect the game's present-interval writes (observed 1→2→1) and correlate timestamps with the frame-rate transition before changing interval semantics.
6. Preserve the existing optimization chain: each new optimized artifact must use the immediately previous successful optimized IPA as its source. Do not restart from the original IPA.

## Status

- Present snapshots: enabled in supplied runtime configuration; two-texture ring confirmed by runtime log.
- Encode thread: enabled in supplied boot configuration and positively described by runtime log; conflicting profile summary requires reconciliation.
- Upstream/host optimization patch: present in Link2iOS source and wired into the optimizer workflow.
- 60→30 FPS root cause: not established by the supplied logs.
- Fix verified on device: no. A new IPA and sustained device A/B capture are still required.

No claim is made that this audit alone fixes the frame-rate drop.
