# Mugiwara4iOS — ONE PIECE: PIRATE WARRIORS 4

**Title ID:** `01008FE00E2F6000`  
**Update Title ID (metadata):** `01008FE00E2F6800`  
**Branch:** `Mugiwara4iOS`  
**Parent:** `SpkIOSzero` at `70807ac56c6b6ea73fa674dec2fbdf384ec122c3`

This branch adapts the SpkIOSzero / Link2iOS pipeline to Pirate Warriors 4. It does not modify, merge, push to, or dispatch the workflows of any other branch.

## Pipeline

1. **Colab package acquisition** — downloads one base package and one update package from the direct URLs supplied by the user. Each can be NSP or XCI; extension and actual content header must agree (NSP `PFS0`, XCI `HEAD` at offset `0x100`). The source scanner groups package contents using their internal content metadata and Title IDs, not their filenames. The selected merged package version must be an update, not `v0`.
2. **Keys and source isolation** — reads the existing `prod.keys` from the configured Drive root, `mugiwara4ios/`, or the existing `spk/` folder. It remains in the Colab runtime and is excluded from the archive. Base/update packages are also excluded from the Drive workspace archive.
3. **NXNative survey and provisional profile** — invokes the pinned `scripts/build_ipa_from_nsp.py` with Title ID `01008FE00E2F6000`. The pinned engine has no registered profile for this title, so NXNative must create `<Title ID>_survey/survey.md` and a generated provisional `game.tsv`. The survey captures content version, ExeFS modules/build IDs, SDK/API/engine markers, RomFS inventory, imports, instruction census and profile guesses.
4. **ARM64 rewrite** — NXNative's own NSO rewrite runs on Colab/Linux. Each rewritten module and its fixup/cut/observation reports are recorded in the preparation manifest. No Kakarot or Sparking! ZERO allocator offset, vtable, module list, memory layout, FPS patch or binary patch is transplanted.
5. **Drive checkpoints** — uploads the compressed build workspace and the merged external `RomFS.img` separately. Both records include byte size and SHA-256. The Mac restore step independently checks the downloaded sizes, hashes, RomFS identity sidecar, Title ID, selected version, profile, rewritten modules and audit files.
6. **GitHub Actions / xcode-27** — only `.github/workflows/mugiwara4_ios.yml` listens for a `handoff.json` push on `Mugiwara4iOS` with the explicit `Queue Mugiwara4iOS build …` commit prefix. It restores the handoff on an Ubuntu validation job, then uses the Apple-Silicon `xcode-27` runner for Route C. No cache is used.
7. **Shader decision is evidence-driven** — Colab records NXNative `profile_guess.py` results and the Mac recomputes them. If the real files require runtime GLSLC capture, the Mac builds/boots the host and captures them. If the files require Unreal shader archive decoding, the Mac performs that decode. A game-owned Oodle helper is built only when `oodle_packs` or `ue_legacy` is positively reported. There is no assumed Unreal PAK version, no copied Kakarot PAK parser, and no guessed shader table.
8. **Metal and Route C** — NXNative splits the detected shader sources, produces the provisional profile's shader map, compiles the iOS Metal libraries, and verifies `c1_full.tsv`, `cb_extent.tsv`, and the `b-<chain>` input stamp against the same chain/profile input digest. It then builds `DmGame.framework`, the Shared Shell, ad-hoc signs it with the increased-memory entitlement, and packages a thin IPA. RomFS, NSP/XCI and keys remain outside the IPA.

## Game-specific constraints

- The expected render path for the KTGL family is NVN, but the pipeline does not assume the title's graphics API: it reads the actual modules/manifest and fails early with the detected reason if this pinned iOS route is not NVN.
- Existing Koei Tecmo/KTGL profiles such as Hyrule Warriors and Fire Emblem: Three Houses are technical references for the *generic host layer only*. Their profile values, module lists, shaders, captures, heap values and frame patches are not copied.
- GLSLC capture, UE decode and Oodle are conditional on the actual survey. A KTGL title is not automatically treated as Unreal.
- No custom `patches.py`, memory override or FPS lock is added before the real Build ID and runtime evidence exist. The first objective is to boot and validate menus/battle; then establish a stable 30 FPS baseline before considering 60 FPS.
- This branch currently expects base + update only. DLC extraction is deliberately not imposed until the base/update path is validated and the supplied packages' content metadata is inspected.
- An IPA build is not proof of iPhone gameplay. Device-side startup, memory pressure, rendering, input and frame pacing remain to be tested after an artifact is produced.

## Colab

Open `colab/Mugiwara4iOS.ipynb` and fill in:

- `DRIVE_FOLDER_ID`: existing configured Drive root.
- `BASE_URL` and `UPDATE_URL`: the user's direct download links.
- `BASE_FILENAME` and `UPDATE_FILENAME`: `.nsp` or `.xci`, matching the downloaded file's real format.

The default Drive lookup reuses `prod.keys` in the current `spk/` folder; it does not move or rewrite it. The notebook downloads packages into the Colab runtime, performs the survey/rewrite and creates separate Drive checkpoints. Its dispatch control is `DISPATCH_TO_GITHUB = False` and stays disabled until the user explicitly enables the final cell.

## Isolation and workflow safety

- This branch was created directly from the inspected `SpkIOSzero` head above.
- All Mugiwara code, Colab notebook, documentation and the workflow are committed only to `Mugiwara4iOS`.
- The workflow filter is restricted to `Mugiwara4iOS` + `handoff.json`; the build job is additionally gated by the explicit Mugiwara queue commit prefix.
- There is no `workflow_dispatch` trigger. A normal code/docs/notebook commit cannot start the build.
- The initial branch setup does not create `handoff.json`, dispatch an event, or start an Action.

## Current validation boundary

The branch scaffolding is prepared, but the actual Pirate Warriors 4 NSP/XCI has not yet been supplied to Colab. Therefore the exact update package version, main Build ID/hash, actual module list, shader counts/captures, memory split, runtime patches and IPA/device result are intentionally not fabricated. They will be generated from the base/update files when their links are supplied.
