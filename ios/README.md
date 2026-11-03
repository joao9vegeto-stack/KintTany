# Asura's Wrath — iOS ARM64 port

Target branch: `Asura'sWiOS`  
Upstream game recompilation: [PauloUbirajara/asuras-wrath-recomp](https://github.com/PauloUbirajara/asuras-wrath-recomp)  
Graphics reference: this repository's `XOWUE` branch and KosmicKrisp iOS WSI patches.

## Current implementation milestone

- Builds from the upstream ReXGlue recompilation source and its pinned submodules. The preparation script resolves the upstream root relative to its own file, so it is independent of the workflow working directory.
- Configures an iOS arm64 application bundle using the upstream SDL3/CAMetalLayer path.
- Builds the KosmicKrisp Mesa ICD for iOS using the exact pinned Mesa revision and iOS Metal WSI patches already used by XOWUE.
- Packages the ICD inside the app and probes its exported ICD entry point / Vulkan instance creation at app startup.
- Produces an **unsigned** IPA artifact; it is not installable until signed with a matching Apple development certificate and provisioning profile.

## Important renderer boundary

The KosmicKrisp probe proves that the iOS driver can be loaded and create a Vulkan instance. It does **not** by itself prove that ReXGlue's Xenos GPU plugin is dispatching its Vulkan calls through this ICD, nor that Asura's Xenos command stream renders correctly. The SDK currently selects its Apple SDL Metal surface path and uses its normal Vulkan provider. A follow-up renderer-provider bridge is required to route that provider through the bundled KosmicKrisp ICD before claiming in-game rendering.

No game assets are included. Import a legally obtained game dump on-device.


## iOS application lifecycle — Play gate (Build 8)

The native UIKit launcher is presented before the ReXApp factory constructs the
game application. Folder selection supplies the game-data path but does not
construct ReXApp or start the guest runtime. Tapping Play completes the factory
gate, injects the selected folder through `OnConfigurePaths`, and only then
continues the existing ReXApp startup. The old `OnFinalizePaths` launcher was
removed because it ran after presentation initialization.
