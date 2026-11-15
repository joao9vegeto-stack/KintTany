# KaKaRoTiOS — DRAGON BALL Z: KAKAROT

Title ID: `010051C0134F8000`

This isolated branch is based on the architecture of `SpkIOSzero` and `Link2iOS`. It does not modify or dispatch workflows from either branch.

## Input: six RAR volume URLs

The Colab notebook `colab/KaKaRoTiOS.ipynb` accepts exactly:

- Base game: RAR volumes 1, 2, 3.
- Update: RAR volumes 1, 2, 3.

The two groups are downloaded into different directories. The source filename is taken from HTTP `Content-Disposition` or the URL. When a host hides the original filename, fill `BASE_PART_NAMES` or `UPDATE_PART_NAMES` with the exact original volume names.

Supported multi-volume layouts:

- Modern: `name.part1.rar`, `name.part2.rar`, `name.part3.rar` (zero-padded numbering is also accepted when consistent).
- Legacy: `name.rar`, `name.r00`, `name.r01`.

The three names must prove they belong to one ordered set. Each group is extracted once by starting UnRAR with its first volume; the extractor follows the other volumes and verifies the archive's file CRC. The script does not concatenate RAR volumes manually. A group must yield exactly one complete `.nsp` or `.xci`; the package is then checked by its actual header (`PFS0` for NSP, `HEAD` at offset `0x100` for XCI), not just its filename.

The source package copies are normalized as `input-packages/base.nsp|xci` and `input-packages/update.nsp|xci`. Their size, SHA-256 and MD5 are recorded.

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

Uploads are recorded with size, SHA-256 and Drive's server-side MD5 checksum. Before deleting the six RAR volumes, Colab writes a small `pipeline/source-manifest.json` checkpoint containing the six URL fingerprints, all six volume hashes, the reconstructed package hashes and the Drive file IDs. If the Colab runtime resets after the package uploads, a new runtime can match the same six link fingerprints and recover base/update from Drive instead of downloading the RAR volumes again. The six downloaded RAR volumes and their extraction scratch are deleted from Colab **only after both reconstructed package uploads have passed verification**. The original packages remain in Drive.

Exactly 20 DLC `.nsp`/`.xci` packages are discovered as direct children of `Drive/<configured-root>/kakarot/`. Their original filenames are retained; there is no `dlc1.nsp`/`dlc2.nsp` naming requirement. The inventory is checked against the supplied size profile (17 around 124 KB and 3 around 106 KB), and each file is header-validated before being staged independently for NXNative. The `prod.keys` file may be in the already-configured Drive root or in its `kakarot/` child, matching the Link2iOS/SpkIOSzero convention. The NXNative `extract_aoc` stage produces AOC images only when those supplied DLC packages are recognized; no DLC data is fabricated.

## Colab / NXNative preparation

1. Download all six RAR URLs, with HTTP Range resume and per-volume SHA-256.
2. Prove each three-volume naming sequence and extract base/update independently using RARLAB UnRAR.
3. Identify the complete NSP/XCI by file header and create normalized base/update package files.
4. Upload base and update to Drive, verify size + server MD5 + local SHA-256, then delete all six RAR volumes.
5. Pass only the reconstructed base and update to the pinned NXNative `scripts/build_ipa_from_nsp.py` scanner/extractor.
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
- `BASE_PART_URLS` — the three direct URLs in volume order.
- `UPDATE_PART_URLS` — the three direct URLs in volume order.
- `BASE_PART_NAMES` / `UPDATE_PART_NAMES` — optional exact source names when the download host does not expose them.

The source URLs themselves are not written into the Drive handoff; only their SHA-256 fingerprints and the volume/package integrity records are retained.

The last notebook cell is deliberately opt-in. `DISPATCH_TO_GITHUB` defaults to `False`. The workflow has no manual dispatch trigger: it runs only after the explicit cell creates a `Queue KaKaRoTiOS build …` commit that changes `handoff.json` on the `KaKaRoTiOS` branch. Ordinary code commits do not start the build.

## Branch and workflow isolation

- Branch base: exact `SpkIOSzero` commit `70807ac56c6b6ea73fa674dec2fbdf384ec122c3`.
- Workflow: `.github/workflows/kakarot_ios.yml`.
- Trigger: `handoff.json` change on `KaKaRoTiOS` with the explicit queue commit message.
- Every job verifies `refs/heads/KaKaRoTiOS`; build runner: `xcode-27`.
- No workflow is triggered while editing the code-only branch.

## Current validation boundary

The six URLs have not yet been supplied or downloaded. Therefore, the actual remote RAR naming scheme, package output extensions/sizes, Kakarot Build ID, update version, module set, PAK inventory, shader count, AOC inventory and device behavior are not yet measured. No successful IPA or iPhone gameplay result is claimed until the real packages pass the Colab survey and the Mac build.
