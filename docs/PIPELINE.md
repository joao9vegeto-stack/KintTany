# Link2iOS technical contract

## Upstream pins
- NX2Apple: `v1.3.1-rc2`
- NXNative: `81906931262fb25d774cce8bca2db8926439e5a2`
- BOTW profile: `dm/games/01007EF00011E000`
- Version: 1.9.0 / `v1114112`
- iOS app: Route C `--shell-framework` + `build_shell.sh`

## Colab/macOS boundary
Colab invokes the pinned NSP builder and stops exactly before `dm/ios/tools/build_ipa.sh`. Linux does not compile Metal, run Xcode, generate PSO archives, use Mac-host runtime shader capture, or emulate the game.

The work archive excludes the large `RomFS.img`, DLC AOC images, original NSPs, `prod.keys`, cached NCA inputs, Linux tools and temporary files. It retains the rewritten modules, extracted ExeFS/control data, NVN shader package/tables, fingerprints and build metadata.

Colab uploads `romfs.img` and each `aoc/<index>.img` to Drive independently. Actions restores those files into the same work paths, downloads the original NSPs and keys, then resumes the pinned builder on macOS.

## IPA contract
The macOS builder uses `--shell-framework`, which implies a separate RomFS and retained extraction. It creates only `DmGame01007EF00011E000.framework`; Route C `build_shell.sh` embeds that framework in the Shared Shell.

The final IPA is inspected to reject `romfs.img`, AOC paths, NSPs and `.mtl4a` files. For the iOS 26 target, the build uses `IOS_PULL=1` and `--gpu none`: ordinary shader libraries remain available to the Metal 4 prebuild path, but a pipeline archive built by the newer SDK is not embedded. The device prepares pipeline bases on first use.

## Credentials
- Colab Secret: `LINK2IOS_GOOGLE_SERVICE_ACCOUNT_JSON`, Drive full scope.
- GitHub Actions secret: `GOOGLE_SERVICE_ACCOUNT_JSON`, Drive read-only in the workflow.
- Fine-grained PAT: used only by the last Colab cell to commit `handoff.json`; repository Contents read/write only.

Neither credential, `prod.keys` nor game data is stored in Git.
