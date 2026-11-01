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
CI may set `KK_SKIP_PREREQUISITES=1` after installing Homebrew dependencies. Output is in `build/`: `libkk-kosmickrisp-ios-arm64.a`, `KosmicKrispM3B`, `include/vulkan/`, `KosmicKrispiOS-build.txt` and SHA-256 evidence.

The build compiles the M3B test application. A compile is not physical-device proof; install/run the M3B smoke IPA on the target iPhone and validate Metal surface creation, swapchain acquire/present, foreground/background, resize and a 10-minute soak.

## Integration
For a custom Vulkan renderer, link the static archive using `-Wl,-force_load,<archive>`, add `build/include` to the header search path and use the static bridge in `Integration/Static`. Link Metal, QuartzCore, UIKit, Foundation and CoreGraphics. For SDL or a loader that expects a dynamic library path, use the dynamic adapter in `Integration/Dynamic`, put `libvulkan.dylib` and `libKosmicKrisp.dylib` side-by-side in Frameworks, and set `SDL_HINT_VULKAN_LIBRARY` to the sandbox path of the shim before SDL initialization.

Every host project still owns its CAMetalLayer, Vulkan surface, swapchain, device/extension negotiation, frame submission, present, drawable resize, app lifecycle, memory policy and shader cache. The driver is not a PS4 runtime or renderer.

## Important limits
- The iOS Mesa patch uses `MTLCreateSystemDefaultDevice()` and requires `MTLGPUFamilyMetal4`; check target-device support.
- Do not silently fall back to MoltenVK or load two providers under the same Vulkan entrypoints.
- The SDK only supplies the Vulkan driver backend. It does not port shadPS4, PS4 CPU execution or system services.
- A symbol probe does not prove Metal WSI or game rendering.
