# KaKaRoTiOS — DRAGON BALL Z: KAKAROT

Title ID: `010051C0134F8000`

This isolated branch is based on the architecture of `SpkIOSzero` and `Link2iOS`. It does not modify or dispatch workflows from either branch.

# Input: three BASE RAR volumes + one direct UPDATE NSP

The Colab notebook accepts exactly four private MegaDL URLs:

- BASE: `part1.rar`, `part2.rar`, `part3.rar`, in order, Title ID `010051C0134F8000`, version `v0`.
- UPDATE: one direct `.nsp`, Title ID `010051C0134F8800`, version `v1048576`, tagged `UPD1.70`.

The notebook asks for the four signed URLs with hidden Colab `getpass` prompts only when a completed Drive handoff cannot be recovered. It validates host, path, Title ID, version, part ordering, NSP suffix and the `download_token` parameter. Raw token-bearing URLs are not written to the public notebook, Git, Drive manifest or Actions handoff. Only URL SHA-256 fingerprints, package metadata and file hashes are retained.

Only BASE is a multipart RAR. Its three path filenames must share a common prefix and be ordered `.part1.rar`, `.part2.rar`, `.part3.rar`; RARLAB UnRAR extracts it once from part 1 and checks archive CRC. The BASE result must be one NSP/XCI with a matching `PFS0` or `HEAD@0x100` header. UPDATE is downloaded directly as one NSP, checked for `PFS0`, size and SHA-256. No UPDATE RAR archive or synthetic RAR volume records are created.

The BASE package is normalized as `input-packages/base.nsp` or `base.xci`; the direct UPDATE is normalized as `input-packages/update.nsp`. Their size, SHA-256 and MD5 are recorded. Each of the 20 DLC files is staged independently with a `dlc_` scanner prefix. The Colab manifest records 22 NXNative inputs; `source.package_count` remains 2 because it counts BASE and UPDATE packages, though only BASE came from RAR.

## Google Drive layout

Each prepared run creates:

```text
KaKaRoTiOS_<request>/
├── games/
│   └── 010051c0134f8000/
│       ├── base.nsp|xci
│       ├── update.nsp|xci
│       ├── romfs.img
│       └── aoc/
│           └── <DLC-index>.img   (only when DLC exists)
└── pipeline/
    ├── source-manifest.json
    └── kakarot-work.tar.zst
```

The workspace archive excludes source packages, `prod.keys`, external `RomFS.img`, and AOC images. Run folders, package uploads, RomFS, AOC and pipeline artifacts are all created under `Drive/kakarot/`. RomFS and AOC are uploaded separately. Base and update are also uploaded as complete package files—not as RAR volumes.

Uploads are recorded with size, SHA-256 and Drive's server-side MD5 checksum. Before deleting the three BASE RAR volumes, Colab writes `pipeline/source-manifest.json` containing the four URL fingerprints, the three BASE volume hashes, both package hashes and Drive file IDs. If Colab resets, a new runtime can match those fingerprints and recover BASE/UPDATE packages from Drive. The three BASE RAR volumes and extraction scratch are deleted from Colab **only after both package uploads have passed verification**; the direct UPDATE NSP remains a separate verified Drive package.

Exactly 20 DLC `.nsp`/`.xci` packages are discovered as direct children of `Drive/<configured-root>/kakarot/`. Their original filenames are retained; there is no `dlc1.nsp`/`dlc2.nsp` naming requirement. The inventory is checked against the supplied size profile (17 around 124 KB and 3 around 106 KB), and each file is header-validated before being staged independently for NXNative. The `prod.keys` file may be in the already-configured Drive root or in its `kakarot/` child, matching the Link2iOS/SpkIOSzero convention. The NXNative `extract_aoc` stage produces AOC images only when those supplied DLC packages are recognized; no DLC data is fabricated.

## Colab / NXNative preparation

1. Validate the three BASE RAR URLs and one UPDATE NSP URL by host, Title ID, version, suffix and part order; collect signed tokens privately in Colab.
2. Download BASE parts 1–3 with HTTP Range resume, per-volume SHA-256 and RAR signature checks; extract once using RARLAB UnRAR and verify CRC.
3. Download UPDATE as one NSP with HTTP Range resume; verify complete transfer, `PFS0` header and SHA-256. No RAR extraction is performed for UPDATE.
4. Upload BASE and UPDATE separately to Drive, verify size + server MD5 + local SHA-256, then delete the three BASE RAR volumes.
5. Pass the reconstructed base/update and all 20 separately staged, header-verified DLC packages to the pinned NXNative scanner/extractor. The scan contract is exactly 22 inputs: one base, one update and 20 DLC packages.
6. Extract the selected update version, externalize RomFS, generate the provisional Kakarot profile, rewrite actual ARM64 modules, and retain the survey, Build IDs and fixup/cut/observation audits.
7. If NXNative extracts AOC data, audit and upload each `.img` separately. Otherwise record zero AOC images.
8. Upload RomFS and the separated workspace, then produce a handoff manifest.

The base and update package files remain local in `/content/kakarot-ios/input-packages` for NXNative. The RAR volumes are removed after Drive package upload, not before.

## Actions / Route C

The `KaKaRoTiOS` workflow restores the workspace and external RomFS, verifies their SHA-256, and re-downloads AOC images (if any) with SHA-256 checks. It checks the stored base/update Drive file metadata (name, size and Drive MD5) without downloading those large source packages again.

The pinned NXNative code then completes the provisional-profile Mac bring-up checks, conditional game-owned Oodle handling, Unreal shader split (including AOC roots when present), iOS Metal compile, chain/table stamp checks, `DmGame.framework`, the Shared Shell, ad-hoc signing and thin IPA packaging.

AOC stays external to the thin IPA and is listed in the build report/Drive handoff for later transfer to the device's `Documents/aoc` when applicable. The RomFS also remains external.

## Running the notebook

Set:

- `DRIVE_FOLDER_ID` — the existing configured Drive root reused from Link2iOS/SpkIOSzero. It must contain one `kakarot/` folder with the 20 named DLC packages; `prod.keys` may be in the root or inside `kakarot/`.
- The four MegaDL signed URLs are collected at runtime through hidden prompts: BASE parts 1, 2, 3, followed by the single UPDATE NSP. Do not paste signed tokens into notebook source or GitHub; they remain in memory only.
- BASE filenames are derived from and validated against their URL paths. UPDATE is stored locally as `update.nsp` and must pass the actual NSP header check.

The source URLs themselves are not written into the Drive handoff; only their SHA-256 fingerprints and the volume/package integrity records are retained.

The last notebook cell is deliberately opt-in. `DISPATCH_TO_GITHUB` defaults to `False`. The workflow has no manual dispatch trigger: it runs only after the explicit cell creates a `Queue KaKaRoTiOS build …` commit that changes `handoff.json` on the `KaKaRoTiOS` branch. Ordinary code commits do not start the build.

## Branch and workflow isolation

- Branch base: exact `SpkIOSzero` commit `70807ac56c6b6ea73fa674dec2fbdf384ec122c3`.
- Workflow: `.github/workflows/kakarot_ios.yml`.
- Trigger: `handoff.json` change on `KaKaRoTiOS` with the explicit queue commit message.
- Every job verifies `refs/heads/KaKaRoTiOS`; build runner: `xcode-27`.
- No workflow is triggered while editing the code-only branch.

## Current validation boundary

The four MegaDL URLs were supplied in the conversation and their path structure is statically validated by the notebook, but this edit did not fetch the signed URLs. Tokens may expire; actual BASE transfer/CRC and UPDATE NSP transfer/header/hash remain unverified until a real Colab run. Package sizes/hashes, Kakarot Build ID, module set, PAK inventory, shader count, AOC inventory and device behavior remain unmeasured. No IPA or iPhone gameplay success is claimed until the real packages pass Colab preparation and macOS build.
