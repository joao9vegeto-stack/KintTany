# KosmicKrispiOS — reusable Vulkan/Metal backend for iOS

Portable build/integration kit for the iOS arm64 KosmicKrisp Vulkan ICD from KintTany's `PsTJohn` work. It is independent of RPCS3, PoPTST, SpartanPort, Android, FEX and Linux rootfs.

## Contents
- `patches/`: exact iOS platform, CAMetalLayer WSI and M3B smoke patches from PsTJohn.
- `smoke/kk_ios_smoke.m`: reference direct-ICD + `VK_EXT_metal_surface` + `VK_KHR_swapchain` application, including swapchain lifecycle.
- `build.sh`: reproducible build of the static iOS arm64 ICD and M3B smoke executable.
- `Integration/`: static and dynamic adapters, probe and CMake helper.
- `Artifacts/`: populated by CI with the built archive, Vulkan headers, manifest and hashes.

## Immutable inputs
| Dependency | Pin |
|---|---|
| Mesa/KosmicKrisp | `bfe063f723d436e5cdef8a98f058d4e44a64810c` |
| SPIRV-LLVM-Translator | `e328468fd329342f1f60c12fdd19cc0faaa88f32` |
| Meson | `1.9.1` |
| LLVM host tools | Homebrew `llvm@20` |
| iOS deployment target | `17.4` |

## Build
On Apple Silicon macOS with Xcode and the iPhoneOS SDK:
```sh
cd KosmicKrispiOS
chmod +x build.sh
./build.sh
```
CI may set `KK_SKIP_PREREQUISITES=1` after installing Homebrew dependencies. Output is in `build/`: the complete iOS static-library set under `build-ios/`, generated `KosmicKrispLink.xcconfig`, `static-link-archives.txt`, `include/vulkan/`, `KosmicKrispiOS-build.txt` and SHA-256 evidence. The M3B smoke harness is compiled separately as a build check.

The build compiles the M3B smoke harness into an object archive only; it does not produce or package a separate smoke IPA. This is not physical-device proof. The harness must be linked into a dedicated test host and run on the target iPhone to validate Metal surface creation, swapchain acquire/present, foreground/background, resize and a 10-minute soak.

## Build dynamic libraries for SDL

After `./build.sh`, run `./make-dylibs.sh`. It creates `build/Frameworks/libKosmicKrisp.dylib` and `build/Frameworks/libvulkan.dylib`, matching the PoPTST adapter's sibling-library layout. Embed both in the consuming app's Frameworks directory and sign them with the app. The build script verifies the exported entrypoints.

## Integration
For a custom Vulkan renderer, link every archive listed in `build/static-link-archives.txt` using the generated `build/KosmicKrispLink.xcconfig` (pass it to `xcodebuild -xcconfig`), add `build/include` to the header search path and use the static bridge in `Integration/Static`. The archives are intermediate build inputs only: Xcode force-loads them into the app's main executable. Link Metal, QuartzCore, UIKit, Foundation, CoreGraphics, libc++ and zlib. Do not flatten nested archives manually or use `-undefined dynamic_lookup`. For SDL or a loader that expects a dynamic library path, use the dynamic adapter in `Integration/Dynamic`, put `libvulkan.dylib` and `libKosmicKrisp.dylib` side-by-side in Frameworks, and set `SDL_HINT_VULKAN_LIBRARY` to the sandbox path of the shim before SDL initialization.

Every host project still owns its CAMetalLayer, Vulkan surface, swapchain, device/extension negotiation, frame submission, present, drawable resize, app lifecycle, memory policy and shader cache. The driver is not a PS4 runtime or renderer.

## Important limits
- The iOS Mesa patch uses `MTLCreateSystemDefaultDevice()` and requires `MTLGPUFamilyMetal4`; check target-device support.
- Do not silently fall back to MoltenVK or load two providers under the same Vulkan entrypoints.
- The SDK only supplies the Vulkan driver backend. It does not port shadPS4, PS4 CPU execution or system services.
- A symbol probe does not prove Metal WSI or game rendering.
