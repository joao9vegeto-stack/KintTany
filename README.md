# PoPTST — iOS retail static-recomp build integration (2026-10-21)

Target: **Xbox retail NTSC only**, native AArch64 iOS; *not* RPCS3 and *not* an Xbox interpreter.
Upstream rePOP `FulGerNet/rePOP`, `reSOT@4ee36260e71d39fd8b02028fd614b1907a0d451b`.
Graphics: pinned SDL3 3.4.18 GPU Vulkan/SPIR-V with actual `ResotGpuQueryAPI` and a real Metal-backed KosmicKrisp ICD from `PsTJohn@db014165` (#125). This path **does not require pretending the Vulkan ICD is a native Metal shader compiler**.

## Implemented source layout

- `.github/workflows/poptst-ios.yml`: one push-triggered Actions run per branch push with two jobs, Linux DXC shader header and macOS Xcode iPhoneOS retail compile/link/archive; final IPA artifact only if each step succeeded. No game XBE or assets enter the CI workspace, logs or IPA.
- `ios/CMakeLists.txt`: builds all actual rePOP retail generated C, target hooks, original runtime, graphics, kernel, APU, input, SDL3 static, and shader-translation libraries, into the real `libPoPTSTRetail.dylib`. Missing inputs and unresolved symbols are build failures.
- `ios/project.yml`: XcodeGen iOS app with retail folder importer and **actual** native runtime linkage, no demo target.
- `ios/App/*`: user-provided retail folder import via Files with SHA-256 and sandbox isolation; live launcher starts actual runtime.
- `ios/Native/poptst_engine.c`, `poptst_ios_fault.c`, `poptst_touch_overlay.m`, `audio_ios.c`, `font_ios.m`: SDL engine/worker, signal/MMIO handler, UIKit Xbox controls and audio/display.
- `ios/Native/poptst_vulkan_icd_bridge.c`: loads verified KosmicKrisp ICD without incorporating RPCS3 engine code.
- `ios/Runtime/poptst_retail_boot.c`: unmodified runtime routines plus actual `xbe_entry_point()`.
- `ios/Tools/patch_repop_ios.py`, `enable_apple_mmio.py`: typed, fail-on-mismatch adaptations of existing upstream Android runtime to Apple arm64 and decoder.
- `ios/Tools/validate_ipa.py`: rejects empty shells missing real native engine, driver, app binary, or embedding the game.

## Verified *here* (Linux)

YAML parsed, Python modules compiled, Swift source frontend parse passed, Vulkan bridge C syntax passed, integration preflight passed. **No Xcode SDK, iOS compilation, device session, or successful IPA exists here**. Compilation and runtime are NOT claimed.

## Real CI procedure

Publish these sources as one initial orphan-root commit to branch `PoPTST` **only** (do not alter other branches); the push triggers `.github/workflows/poptst-ios.yml` once. It downloads the *already-tested* KosmicKrisp driver from Actions #125, builds rePOP retail code and the SDL Vulkan renderer, links the iOS host, packages and verifies `PoPTST-retail-ios.ipa`. If any native platform incompatibility remains, the job must fail: no fake success IPA.

The iOS application imports, from the owner's files:

```
xbox-retail/default.xbe  SHA-256 753C58B191279BF4D1A8B28A936DF36AA222ED566487AB1FBDFCD090E91EE379
xbox-retail/prince.bf
xbox-retail/shaders.bin
xbox-retail/VIDEO/, SOUND/, MEDIA/, POP1/, POP2/
```

**Risk register (not solved by static source checks):** Darwin memory/reservation semantics, unhandled A64 MMIO instruction families, SDL Vulkan window swapchain on SwiftUI-hosted UIKit, dynamic shader compiler glslang linkage, original rePOP translated stubs/noops, Metal driver actual retail query behavior. These must be evaluated from one actual Actions log plus iPhone device logs, not assumed resolved.
