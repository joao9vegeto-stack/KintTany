# Link2iOS technical contract

## Fixed source input

The Colab notebook is preconfigured for Drive folder `19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm`. At the root, keep `prod.keys`, only `update.nsp`, `dlc1.nsp` and `dlc2.nsp` as NSP inputs; all other root files and folders are ignored. No manual `base/`, `update/`, or `dlc/` directories are required.

For the first run, the notebook collects the signed 7z URL through a masked prompt. The URL is not committed to this public repository, echoed, or copied to Drive. Colab downloads the archive to temporary runtime storage, validates the 7z signature and archive paths, tests it, and extracts it with 7-Zip. It requires exactly one XCI with the XCI `HEAD` magic at offset `0x100`, then uploads only that XCI to a generated `BOTW_Base_XCI/` folder in Drive. The original 7z and extracted staging directory are removed from the Colab runtime.

Colab downloads `prod.keys` and the three NSPs (the exact update/DLC filenames and two DLCs) from the Drive root into temporary runtime storage. The key is used to read the XCI/NSP content metadata and decrypt NCAs; the XCI, three NSPs and key are removed from the Colab runtime after Linux preparation. The extracted base XCI remains in `BOTW_Base_XCI/`; subsequent runs reuse it without downloading the 7z again.

The input is BOTW base XCI + update 1.9.0 + `dlc1.nsp` + `dlc2.nsp`, Title ID `01007EF00011E000`, package `v1114112`. The pinned NXNative builder supports XCI directly and scans it together with the update/DLC NSPs; no XCI-to-NSP conversion is performed. Both DLC NSPs are required, and NX2Apple must produce AOC RomFS images or preparation fails.

## Upstream pins
- NX2Apple: `v1.3.1-rc2`
- NXNative: `81906931262fb25d774cce8bca2db8926439e5a2`
- BOTW profile: `dm/games/01007EF00011E000`
- Version: 1.9.0 / `v1114112`
- iOS app: Route C `--shell-framework` + `build_shell.sh`

## Colab/macOS boundary

Colab invokes the pinned XCI/NSP package builder and stops exactly before `dm/ios/tools/build_ipa.sh`. Linux does not compile Metal, run Xcode, generate PSO archives, use Mac-host runtime shader capture, or emulate the game.

The work archive excludes the large `RomFS.img`, DLC AOC images, original XCI/NSP packages, `prod.keys`, cached NCA inputs, Linux tools and temporary files. It retains rewritten modules, extracted ExeFS/control data, the NVN shader package, profile tables, fingerprints, and the exact shader-package content key and Metal chain.

Colab uploads `romfs.img` to Drive independently. It uploads the AOC images produced from both root-level DLC NSPs; an empty AOC result is rejected. GitHub Actions restores the workspace and RomFS, plus AOC images when present. NSPs and `prod.keys` never enter the Actions runner. The `RomFS.img.id` sidecar produced by NX2Apple's image-identity patch remains beside the restored image.

## IPA contract

On macOS, the pinned NXNative helpers validate the Colab shader-package key and chain, compile the iOS Metal libraries from the prepared `shader/pkg`, then call `dm/ios/tools/build_ipa.sh` with `DM_FRAMEWORK_ONLY=<folder>`. This is the final stage of the same `--shell-framework` route used by Colab: it creates only `DmGame01007EF00011E000.framework` and does not re-scan NSPs or re-extract, rewrite, or split the game. Route C `build_shell.sh` then embeds that framework in the Shared Shell.

The final IPA is inspected to reject `romfs.img`, AOC paths, NSPs, `prod.keys` and `.mtl4a` files. For the iOS 26 target, the Metal builder uses `IOS_PULL=1` and `DM_PSO_GPUS=none`: ordinary shader libraries (including pulling variants) remain available to the Metal 4 path, but a PSO archive built by the newer SDK is not embedded. The device prepares pipeline bases on first use.

## Credentials

- Colab: interactive Google OAuth via `auth.authenticate_user()`; the signed-in account must have access to the configured Drive folder. No Colab service-account Secret is required.
- GitHub Actions secret: `GOOGLE_SERVICE_ACCOUNT_JSON`, Drive read-only.
- Fine-grained PAT: used only by the last Colab cell to commit `handoff.json`; repository Contents read/write only.
- The signed 7z URL is supplied at runtime and is never stored in Git.

Neither credential, `prod.keys` nor game data is stored in Git.


## Recovery and measured transfers

A successful Colab run stores a small `handoff.json` manifest in the top-level `Link2iOS_BOTW_*` Drive folder alongside the `pipeline/` and `games/` subfolders. The notebook's recovery step scans only those BOTW run folders, validates project/title/version, workspace ID, RomFS ID and non-empty AOC records, and restores the local handoff JSON. It does not download XCI/NSPs, re-extract packages, rewrite modules, or split shaders. Kleo2iOS folders and artifacts are ignored.

Within the same Colab runtime, `/content/link2ios/work`, the pinned NX2Apple checkout, and previously downloaded package files are retained between retries. Matching Drive package files are reused after checking size and Drive MD5 when available. Transfer logs report actual byte counts, elapsed time and measured average throughput; OAuth and Git clone time are not represented as game-data transfer.


## BOTW 1.9.0 package and DLC contract

The Colab stage invokes the pinned NXNative `scripts/build_ipa_from_nsp.py` through its normal `parse_args()` and `main()` flow, with `--title-id 01007EF00011E000 --package v1114112 --shell-framework`. NXNative scans package content metadata, chooses the base XCI and update 1.9.0, extracts their combined RomFS/ExeFS, rewrites the profile's AArch64 modules, extracts each AddOnContent NCA with its own `nx_extract --aoc` call, and includes the DLC RomFS roots in the NVN shader split. This is the builder's real package path; the notebook does not manually merge NSP/XCI contents.

For BOTW, AddOnContent title IDs `01007EF00011F001` and `01007EF00011F002` must become `aoc/1.img` and `aoc/2.img`. Colab, the Drive handoff, Actions restore and the macOS framework build all require exactly those two non-empty images. A one-DLC or missing-DLC build is rejected before IPA packaging.
