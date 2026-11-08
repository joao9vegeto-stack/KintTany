# Pipeline contract

Colab runs the pinned NXNative builder through NUP scan/validation, extraction to work/extract/vN, AArch64 module rewriting into work/patched_vN, and offline NVN shader splitting/profile-table validation into work/shader/pkg.

The Linux adapter intercepts the builder immediately before dm/ios/tools/build_ipa.sh. It deliberately skips iOS Metal compilation, pipeline-archive compilation and Xcode. The macOS job resumes the same NUP and work directory; upstream fingerprints decide which preparation stages can be reused.

The macOS finalizer runs build_ipa_from_nsp.py --framework --romfs separate --gpu g18p. The patched Xcode project builds DmGame<TITLE_ID>.framework; the Shared shell exporter embeds that framework in DmShell.app and packs NX2Apple.ipa.

The handoff archive contains game.nup, work/ (extraction, rewritten modules, shader package/tables, logs and prep manifest) and manifest.json (title ID, package version and pinned engine identity).

No game dump, NUP, RomFS, keys or other proprietary game data is stored in Git.
