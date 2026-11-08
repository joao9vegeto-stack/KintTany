# Pipeline contract

Colab runs the pinned NXNative builder through NUP scan/validation, extraction to work/extract/vN, AArch64 module rewriting into work/patched_vN, and offline NVN shader splitting/profile-table validation into work/shader/pkg.

The Linux adapter invokes the builder with --shell-framework and intercepts it immediately before dm/ios/tools/build_ipa.sh. It deliberately skips iOS Metal compilation, pipeline-archive compilation and Xcode. The macOS job resumes the same NUP and work directory; upstream fingerprints decide which preparation stages can be reused.

The macOS finalizer runs build_ipa_from_nsp.py --shell-framework <folder> --gpu g18p. This creates the title-specific DmGame<TITLE_ID>.framework with code, tables, profile, settings, shader libraries, optional pipeline archive and icon. Then dm/ios/tools/build_shell.sh --build generates the Route C shell project and compiles DmShell.app with all game frameworks embedded but not linked. The app is ad-hoc signed (frameworks first, app executable with Increased Memory Limit entitlement), then packed by dm/ios/tools/pack_ipa.py.

The handoff archive contains game.nup, work/ (extraction, rewritten modules, shader package/tables, logs and prep manifest) and manifest.json (title ID, package version and pinned engine identity).

No game dump, NUP, RomFS, keys or other proprietary game data is stored in Git.


## iPhone game-data import

The Shared shell already includes the upstream iOS game-data picker and bookmark support. It resolves a game's RomFS from the per-game app folder (`Documents/games/<title ID>/`) or from a location selected in the game details screen. A selected `romfs.img` or RomFS folder is kept through a security-scoped bookmark; a re-signed sideload may require selecting it again.

The build exports `game-data.zip` (ZIP64, stored/no recompression) with this layout:

```
games/<title ID>/romfs.img
games/<title ID>/aoc/   (when present)
```

On iPhone, extract `game-data.zip` in Files, open NX2Apple, open the Bananza game details, choose **Game data → Choose game data…**, and select the extracted `romfs.img` (or its containing RomFS folder if offered). The shell's existing data resolver then supplies `DM_ROMFS` to the game at launch. The archive itself is not read by the game engine and is not embedded in the IPA.

This import path is user-driven; the build does not silently copy a multi-gigabyte image into the app sandbox at first launch.
