# Dante2iOS - Devil May Cry 2 (Switch NSP base to iOS 26)

The scope of this port is exclusively branch **Dante2iOS** of joao9vegeto-stack/KintTany. No other branches are modified.

- Title ID: **01007CF00D5BA000** (Devil May Cry 2, Nintendo Switch).
- Package: **base NSP v0 only**; no update and no DLC.
- Engine: seedds/nxnative **b526a50b85e4cfa3142c111e1ad491d9fd11f0eb** plus the tested Dante2iOS patches.
- Platform: Shared Shell minimum deployment **iOS 26.0**. No iOS 27 offline Metal PSO archives.

## Colab to Drive to Actions to Drive

Open the companion notebook **Dante2iOS_DMC2.ipynb** in Colab. It is adapted from the uploaded Link2iOS BOTW notebook and retains its 13-cell workflow.

The previously used shared parent Drive folder is **19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm**. The source must be in its **dmc2** subfolder: exactly one base NSP, directly or at most one subfolder deep, or one 7z containing exactly one NSP. Provide prod.keys in the dmc2 subfolder or shared parent. Never mix other game's NSPs into the dmc2 folder.

1. Authenticate Drive and clone branch Dante2iOS (not another branch).
2. Recover an existing checkpoint or run the real upstream **scripts/build_ipa_from_nsp.py** with the base-only Title ID and package v0. When no registered game profile exists, the builder performs a survey and writes a **provisional profile**. It extracts RomFS, rewrites AArch64 modules, and prepares NVN shaders offline where possible.
3. Colab uploads RomFS.img **separately** into dmc2/Dante2iOS_DMC2_<request>/games/<titleid>, plus a compressed work archive and SHA-256 manifest. The archive omits the original NSP, prod.keys and RomFS.
4. The notebook submits one **dmc2/handoff.json** commit to Dante2iOS (not main). Only the DMC2 workflow listens to that path. It validates the original Title ID, version, pin, GPU backend, RomFS identity and workspace checksums.
5. The macOS xcode-27 runner compiles the actual **DmGame01007CF00D5BA000.framework**, then the **current** Shared Shell at **frontend-ios/Shell/build_shell.sh**, then signs and produces **Dante2iOS-DMC2.ipa** plus **build-report.json** as GitHub Actions artifacts.
6. Run the notebook's **first cell last**, after a successful DMC2 Actions IPA exists. It selects the latest DMC2-only successful workflow, checks the generating commit and artifact SHA-256, then transfers that IPA into dmc2 in Google Drive.

## Compatibility and integrity boundaries

**No original NSP or prod.keys is uploaded to GitHub Actions or embedded in the IPA.** The iPhone receives a thin IPA with external game data through the Shared Shell's Files workflow. DM_COPY_ROMFS=NO, DM_PSO_GPUS=none and no .mtl4a archives protect iOS26 compatibility. Increased Memory Limit is requested by the Shared Shell; final sideload re-signing must retain it to use it.

If a game-owned shader decoder, Mac host runtime capture or JIT capture is required, the initial Linux route **fails with diagnostics**. No placeholder shader maps, fake profiles, fake IPA, or unsupported 60 FPS guarantee are produced. A **provisional** profile and a successful IPA build do not imply the game boots: actual iPhone logs are required for bring-up.

### Critical iOS shader and RomFS packaging checks

- **Do not use the original 31 MB IPA from run 44700530368.** It contains `shader_map.tsv`, but it does not contain `msl/b-0724088d3779.img`. The Shared Shell marks the data as needing an update even if the RomFS file is valid when its game shaders are missing.
- The Actions finalizer now bundles the *real iPhone Metal compilation output*, `shader/ios/b-<chain>.img`, inside `DmGame01007CF00D5BA000.framework/msl/` **before** signing. It tests file existence, size and SHA-256 at the framework, Xcode app, and published IPA layers. No RomFS, NSP or keys are added to the IPA.
- To provide the external RomFS in the **actual DmShell application Documents container**, use `Documents/games/01007CF00D5BA000/romfs.img`. Alternatively, place it directly inside `Documents/romfs.img` for the Shell's identity-based automatic claim, or use the game's **Choose folder** setting to select the directory containing it.
- The correct Colab-generated `romfs.img` has exactly **1,889,696,967 bytes**, SHA-256 `17c022b7ef22e11b765d78cf0041c6edcb8903e076e053395f80ea024601fa7a`, and starts with `DMROMFS1`. A generic unpacked Switch RomFS or a different `romfs.img` will not match the compiled manifest's identity. The Shell does not require a separate `RomFS.img.id` file on the phone.
- The IPA build report states its embedded shader asset checksum and required RomFS identity. A successful build does not prove gameplay; install and collect the **in-game** log once the Shell reports Play available.

The initial scripts-only commit triggers a **validation-only** DMC2 run (no handoff, so no attempted IPA build). Only after a real Colab preparation and subsequent handoff commit does Actions attempt the full build. A successful game build can then be copied to Drive with the notebook's transfer cell.

### DMC2 first-device video/AudioOut fix (2026-11-20)

First iPhone bring-up successfully mounts the 1.89 GB RomFS, loads the signed iOS shader image, executes the menu/intro at around 60 FPS, and decodes H.264/AAC video through the existing host movie path. After the movie is stopped, the guest called `nn::audio::FlushAudioOutBuffers(nn::audio::AudioOut*)` at `sdk+0x93600`; its original SDK implementation dereferenced an uninitialized native audout-service proxy at `sdk+0x93684` (`SIGSEGV addr=0`). The game uses NXNative host AudioOut instead of the Switch audout service.

The branch-only patch `0072-dante2ios-flush-audioout-after-movie-stop.patch` adds the missing **HLE_FORCE** API, flushes pending buffers through the real host AudioOut queues (or safely no-ops if already closed), and stops/restarts active consumers under the existing audio lock. The new macOS materialization preflight requires the exact hook and critical lifecycle calls before running the expensive framework build. No Colab re-extraction/shader split is needed; reuse the same handoff. This addresses the measured native SDK null dereference, not all possible movie-decoder or video-shader issues. The device log also reports a separate NVN Metal varying mismatch on vertex `8bdbcfee10f406ac_b` and fragment `6235a86d82af4151_b` (`user(locn4)`); do not mistake it for the audio crash. Run on device and collect a new crash/log before claiming stable gameplay.
