# Pipeline contract

Colab runs the pinned NXNative builder through NUP scan/validation, extraction to work/extract/vN, AArch64 module rewriting into work/patched_vN, and offline NVN shader splitting/profile-table validation into work/shader/pkg.

The Linux adapter invokes the builder with --shell-framework and intercepts it immediately before dm/ios/tools/build_ipa.sh. It deliberately skips iOS Metal compilation, pipeline-archive compilation and Xcode. The macOS job resumes the same NUP and work directory; upstream fingerprints decide which preparation stages can be reused.

The macOS finalizer runs build_ipa_from_nsp.py --shell-framework <folder> --gpu g18p. This creates the title-specific DmGame<TITLE_ID>.framework with code, tables, profile, settings, shader libraries, optional pipeline archive and icon. Then dm/ios/tools/build_shell.sh --build generates the Route C shell project and compiles DmShell.app with all game frameworks embedded but not linked. The app is ad-hoc signed (frameworks first, app executable with Increased Memory Limit entitlement), then packed by dm/ios/tools/pack_ipa.py.

The handoff archive contains game.nup, work/ (extraction, rewritten modules, shader package/tables, logs and prep manifest) and manifest.json (title ID, package version and pinned engine identity).

No game dump, NUP, RomFS, keys or other proprietary game data is stored in Git.
