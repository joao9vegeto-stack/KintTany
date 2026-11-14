# KaKaRoTiOS — DRAGON BALL Z: KAKAROT

Title ID: `010051C0134F8000`

This branch is an isolated Kakarot pipeline based on the architecture of `SpkIOSzero` and `Link2iOS`. It does not modify or dispatch workflows from either branch.

## Pipeline

1. **Colab source acquisition** — download one base package and one update package from user-supplied direct URLs. Each package may independently be `.nsp` or `.xci`. The content header is validated before continuing. `prod.keys` is read from the configured Drive root or its `kakarot/` folder and stays in the Colab runtime.
2. **NXNative survey and extraction** — use the pinned `scripts/build_ipa_from_nsp.py` content-meta scanner and extractor. The Title ID is selected from the package metadata, not inferred from filenames. The tool extracts the merged update version, writes the RomFS image and sidecar, surveys ExeFS/SDK/graphics/engine markers, and generates a provisional `game.tsv` when no Kakarot profile exists.
3. **ARM64 rewrite** — the NXNative rewriter translates the actual Kakarot modules and records build IDs, fixups, cuts and observations. No Sparking! ZERO Build ID, allocator offset, vtable, module list or memory layout is copied. Those facts must be discovered from the actual Kakarot package and verified on the Mac.
4. **Drive checkpoint** — the workspace archive and `RomFS.img` are separate Drive objects. Each upload is recorded with byte size and SHA-256. The workspace excludes the original NSP/XCI files, `prod.keys`, and the external RomFS image.
5. **GitHub Actions / macOS ARM64** — only the `KaKaRoTiOS` workflow restores the workspace and external RomFS, verifies size and SHA-256, and checks the provisional profile and rewritten modules against the Colab manifest.
6. **Unreal shader path** — the pinned NXNative reader explicitly supports Unreal PAK version 8 (UE 4.22–4.25), the format documented for Kakarot. The pipeline re-audits PAK versions, index encryption and compression methods on Colab and macOS. PAK v8 Zlib/Stored inline shader data is read by `uepak.py`; a game-owned Oodle host is built only when the actual package audit/classifier proves an Oodle-backed path is present. The Mac stage performs any required game-owned Oodle decode and then the shader split.
7. **Metal and Route C** — build the iOS Metal libraries for the generated profile, then verify the `b-<chain>` library stamp, `c1_full.tsv`, and `cb_extent.tsv` all name the same chain and profile-input digest. Build `DmGame.framework`, the NX2Apple Shared Shell, ad-hoc sign it with the increased-memory entitlement, and package a thin IPA without RomFS, packages, or keys.

## Kakarot-specific constraints

- The first run generates a **provisional** profile from the exact supplied base/update files. It is expected to require bring-up and corrections after the first Mac build.
- No Sparking! ZERO allocator patch is transplanted. Unreal allocator layout, call sites, memory region and heap settings are game/build-specific; they must be measured before adding a Kakarot-specific patch.
- The base and update are mandatory. No DLC contract is imposed. DLC support can be added later after the base + update path is stable and the package metadata is inspected.
- The shader source decision is data-driven. PAK v8 is a strong prior from upstream's Kakarot-specific reader support, not permission to skip the package audit.
- An iPhone IPA build is not the same as gameplay validation. Device runtime, memory pressure, rendering, input and frame pacing still need to be tested on the target iPhone after the artifact exists.

## Running the Colab notebook

Open `colab/KaKaRoTiOS.ipynb`. Fill in:

- `DRIVE_FOLDER_ID` — the configured Drive root containing `prod.keys` (or a `kakarot/` child with the key file).
- `BASE_URL` and `UPDATE_URL` — direct download URLs for the user's own packages.
- `BASE_FILENAME` and `UPDATE_FILENAME` — use `.nsp` or `.xci` to match each package's real format.

The last notebook cell is deliberately opt-in. It defaults to `DISPATCH_TO_GITHUB = False`. Dispatch writes `handoff.json` to `KaKaRoTiOS` only. Do not dispatch until the URLs and source packages are ready.

## Branch and workflow isolation

- Branch base: the exact `SpkIOSzero` commit `70807ac56c6b6ea73fa674dec2fbdf384ec122c3`.
- Workflow: `.github/workflows/kakarot_ios.yml`.
- Push trigger: `handoff.json` changes on `KaKaRoTiOS` only.
- Every job checks `refs/heads/KaKaRoTiOS`; build runner: `xcode-27`.
- No workflow is run by the code-only branch commit. The workflow is not manually dispatched during setup.

## Current validation boundary

The scripts and notebook are prepared for the user-supplied packages. Until the base/update URLs are supplied and the Colab preparation is run, the real Kakarot Build ID, exact update version, module set, PAK inventory, shader count, memory behavior, and device performance remain unmeasured. No successful IPA or iPhone gameplay result is claimed at this stage.
