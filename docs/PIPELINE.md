# Link2iOS technical contract

## Upstream pins
- NX2Apple: `v1.3.1-rc2`
- NXNative: `81906931262fb25d774cce8bca2db8926439e5a2`
- BOTW profile: `dm/games/01007EF00011E000`
- Version: 1.9.0 / `v1114112`
- iOS app: Route C `--shell-framework` + `build_shell.sh`

## Colab/macOS boundary
Colab invokes the pinned NSP builder and stops exactly before `dm/ios/tools/build_ipa.sh`. Linux does not compile Metal, run Xcode, generate PSO archives, use Mac-host runtime shader capture, or emulate the game.

The work archive excludes the large `RomFS.img`, DLC AOC images, original NSPs, `prod.keys`, cached NCA inputs, Linux tools and temporary files. It retains rewritten modules, extracted ExeFS/control data, the NVN shader package, profile tables, fingerprints, and the exact shader-package content key and Metal chain.

Colab uploads `romfs.img` and each `aoc/<index>.img` to Drive independently. GitHub Actions restores only those external files and the prepared workspace. NSPs and `prod.keys` never enter the Actions runner. The `RomFS.img.id` sidecar produced by NX2Apple's image-identity patch remains in the workspace beside the restored image.

## IPA contract
On macOS, the pinned NXNative helpers validate the Colab shader-package key and chain, compile the iOS Metal libraries from the prepared `shader/pkg`, then call `dm/ios/tools/build_ipa.sh` with `DM_FRAMEWORK_ONLY=<folder>`. This is the final stage of the same `--shell-framework` route used by Colab: it creates only `DmGame01007EF00011E000.framework` and does not re-scan NSPs or re-extract, rewrite, or split the game. Route C `build_shell.sh` then embeds that framework in the Shared Shell.

The final IPA is inspected to reject `romfs.img`, AOC paths, NSPs, `prod.keys` and `.mtl4a` files. For the iOS 26 target, the Metal builder uses `IOS_PULL=1` and `DM_PSO_GPUS=none`: ordinary shader libraries (including pulling variants) remain available to the Metal 4 path, but a PSO archive built by the newer SDK is not embedded. The device prepares pipeline bases on first use.

## Credentials
- Colab Secret: `LINK2IOS_GOOGLE_SERVICE_ACCOUNT_JSON`, Drive full scope.
- GitHub Actions secret: `GOOGLE_SERVICE_ACCOUNT_JSON`, Drive read-only in the workflow.
- Fine-grained PAT: used only by the last Colab cell to commit `handoff.json`; repository Contents read/write only.

Neither credential, `prod.keys` nor game data is stored in Git.
