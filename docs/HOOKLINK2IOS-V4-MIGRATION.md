# HookLink2iOS — genuine HookLink 4.0 / nxnative X3 migration (2026-11-23)

## Source versions / scope

- Release: HookLink **4.0 / X3**, upstream [dsi-hub/HookLink@b5c41acf](https://github.com/dsi-hub/HookLink/tree/b5c41acf469edb99abc5156f1f6f18397261f54a).
- Authoritative engine version from HookLink's **Resources/engine.json**: [dsi-hub/nxnative@ee3ce6a02bc737d38795f0a96cce494cee7a799c](https://github.com/dsi-hub/nxnative/tree/ee3ce6a02bc737d38795f0a96cce494cee7a799c) (branch hooklink).
- Shader ABI: `b6112b954691`; tool lock `dmsh_chain.lock`. Different from the existing 1.8.5 image `b-2afd39090b76`. **They are not interchangeable.**
- Input: previously verified 25,622,267,860-byte NUP (SHA-256 `85b08e81a2a08612f88de1063c8581fe088f7554303aa1ff207972d729b5916f`), update v131072; the original handoff is treated strictly as a **source manifest**, not as a prebuilt X3 shader workspace.
- Output: iOS 26, Xcode 27.2, `--gpu none`, ROMFS/AOC external, signed ad-hoc with increased-memory entitlement, 30/60 FPS selectable. No PSO offline archive.
- New rebuild workflow: `.github/workflows/hooklink2ios-v4.yml`; source: `scripts/hooklink2ios_v4_build.py`. It is independent of `hooklink2ios-native-relink.yml` (the old 1.8.5 compatibility branch of builds).
- Real 4.0 changes from upstream include complete NDSR->MetalFX chain, `DM_NVN_TEX_MIP_SKIP` memory saver, fixed pool-retirement lifetime, shader translator changes, profile `pool_skip_retired=on`, 16-GiB virtual alias range and iPhone dynamic-resolution variants. The upstream Mac GUI redesign is not an iOS launcher replacement; only the native runtime's settings/features are included.

## Stability / regressions

The iPhone log from 2026-11-23 showed `MapPhysicalMemory ... ResultLimitReached` (6.96 GB held / 0.68 GB free) and a black 3D scene with the HUD alive. The 1.8.5 selective NDSR bypass was disabled as a fallback in `d3a19eec`; this X3 path instead uses the **original fully matched upstream 4.0 code** against the **matching new X3 shader image**. No 1.8.5 NDSR/MetalFX backport is applied.

The v4 pipeline rebuilds translated guest shaders using its own cache generation `cas-b6112b954691.db`, with SQLite snapshots uploaded to the Drive run folder every 15 minutes and validated before resume. The old 1.8.5 cache cannot qualify as X3. Saving/preserving input files and output has SHA-256 and ZIP/Metal image/romfs.id checks. The extracted NUP can be removed only after v4 completed AOC extraction, with a source anchor checked **before** downloading 25.6 GB.

Host preflight must pass exact engine SHA, profile, new shader chain, iOS project target and toolchain before moving any big data. A new IPA is only valid after workflow success **and on-device testing** across area changes, resolution changes, low-memory states, scene 3D and HUD, frame generation, save loading, 30/60 FPS. Build success alone does not establish that the black-scene regression is resolved.

## Performance defaults

Follow HookLink X3's launcher defaults on iPhone: `DM_QOS_MAP_DEFAULT=1`, `DM_DYNRES_DEFAULT=1`, `DM_THERMAL_CAP_DEFAULT=0`, `DM_FRAME_MODE_DEFAULT=2` (30 + FG, user selectable) and `DM_FRAMEGEN_SCALE_DEFAULT=0.75`. Upstream X3 enables texture mip skipping by default on iPhone (`DM_NVN_TEX_MIP_SKIP`), with shadow map half and GPU occlusion experimental/off by default.

## Current workflow limitation

The new pipeline initially uses the verified NUP in Drive and performs the nxnative full build on the macOS runner. This reuses the **proven** NUP/Drive/Xcode path while upgrading ABI; it is not yet the optimized Colab-prepared-Linux-workspace → macOS-only-finalization architecture. That split requires versioned re-preparation under X3, not reusing the 1.8.5 workspace. Do **not** advertise this migration as Colab-offloaded or shader-rebuild-free.
