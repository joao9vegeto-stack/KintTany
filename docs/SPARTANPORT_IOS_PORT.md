# SpartanPort for iOS — engineering baseline

Status: SpartanPort iOS shell links the pinned KosmicKrisp iOS arm64 static dependency set into its app executable and probes ICD entrypoints/instance extensions at launch. The current display view still performs a direct Metal clear; the Vulkan Metal-surface/swapchain smoke renderer has not yet been integrated into the SwiftUI screen. The reusable SDK lives in `KosmicKrispiOS/`; CI publishes one unsigned SpartanPort IPA and the reusable SDK as a separate artifact. No playable PS4 runtime is claimed; game-start remains disabled.

## Scope

Port the SpartanPort God of War III Remastered (PS4) runtime to iPhone/iPad ARM64. The app must accept a user-provided, legally dumped game directory and must not bundle game data. The target is an iOS-native application and runtime, not an Android APK wrapper, Linux rootfs, FEX container, or remote-streaming client.

Upstream references:
- Android ARM64 branch: https://github.com/zFitness/gow3_android/tree/arm
- ARM64 README (Portuguese): https://github.com/zFitness/gow3_android/blob/arm/README.pt-BR.md
- AOT instructions documented by upstream: https://github.com/zFitness/gow3_android/blob/arm/README.zh.md
- Upstream releases: https://github.com/zFitness/gow3_android/releases

## Verified architecture facts

1. The regular Android ARM64 branch does **not** run the PS4 x86-64 guest code natively. Its documented runtime is FEXCore (x86-64 guest execution on ARM64), while the graphics path is shadPS4 → Vulkan. The Android package also expects the nixport host/rootfs and Turnip/Vulkan 1.3.
2. The upstream README documents an experimental AOT path named `feature/aot-native-arm64`, with `tools/aot/build-recompiler.sh` and `tools/aot/compile-game.sh`. The branch is not currently discoverable in the upstream repository's published branch list. Treat this as an unverified/unavailable dependency until its source is published or supplied; do not fabricate its contents or assume it can be built.
3. The PC runtime is described upstream as running the PS4's x86-64 executable directly on x86-64 hardware. iPhone/iPad use ARM64, so the PC executable cannot simply be linked as an iOS app.
4. The Android/Linux GPU implementation is Vulkan-based and depends on shadPS4. iOS has no system Vulkan API. A MoltenVK compatibility layer may be useful for an early experiment, but it is not proof that shadPS4's complete Vulkan feature set, synchronization, memory model, shader pipeline, or presentation path works on iOS.
5. The existing KintTany target is a SwiftUI app with an existing unrelated product UI. This branch must keep the work isolated; do not replace unrelated application behavior or touch other branches.

## Source-level review pinned to upstream `arm` commit `53afee63597b10a5a1f250cdb62dd4390caa13f1`

- `cpu/guest_cpu_fex.cpp` creates FEXCore contexts and uses its JIT/code-cache plus Linux signal/ucontext facilities. The published ARM64 branch is not a native AOT CPU implementation.
- `cpu/gportcpu.cmake` links `FEXCore`, `Common`, `JemallocLibs` and `fmt`; it produces `libgportcpu.so`.
- `gpu/CMakeLists.txt` requires Vulkan, SDL3 and X11 on non-Windows builds, in addition to shadPS4 renderer/recompiler and shader tooling. This is not an iOS Metal backend and cannot be assumed to compile unchanged for iOS.
- `src/runtime_memory.c` reserves a large PS4 guest virtual-address range and uses platform-specific mappings. The POSIX path relies on `mmap`/`mprotect`; the Windows path has a separate placeholder/section implementation. iOS address-space placement, executable mappings and memory pressure need a dedicated design and device tests.
- The upstream ARM64 CPU adapter is GPL-2.0-or-later. No upstream source has been copied into this iOS shell; license compatibility and notices must be resolved before importing runtime code.

## KosmicKrisp backend reused from PsTJohn

The graphics provider is the user's existing KosmicKrisp/Mesa port from `PsTJohn`, not a replacement MoltenVK backend. `KosmicKrispiOS/` contains the pinned Mesa build, M2 iOS platform patch, M3 Metal WSI patch, M3B smoke-target patch, reference CAMetalLayer test, static/dynamic adapters and CMake integration helper. Meson emits the KosmicKrisp ICD and its transitive Mesa/Vulkan dependencies as multiple iOS static archives. Building only `libkk.a` is insufficient: the prior Xcode link exposed thousands of unresolved Mesa utility, BLAKE3, hash-table, mutex, C11-thread and WSI symbols. CI now discovers and builds every static-library target registered in the iOS Meson graph, verifies representative implementations from the actual failure logs across those archives, and generates `KosmicKrispLink.xcconfig` to force-load each archive directly into the SpartanPort app executable. The M3B smoke object archive is build-only and is excluded from production linking. No nested-archive flattening, separate KosmicKrisp executable/dylib, or `-undefined dynamic_lookup` is permitted. CI compiles the M3B smoke harness as an object archive build check but does not link it into the production app or package a second IPA. Physical-device surface/swapchain presentation remains pending. A compile or extension probe is not evidence of game rendering.

## Required porting work

### P0 — make the source reproducible
- Pin the exact upstream commit and all submodule revisions used for the Android branch.
- Obtain and pin the real AOT branch/recompiler source, or formally choose a separately licensed and reproducible AOT toolchain.
- Record the AOT output format, relocation model, imported PS4 symbols, exception/unwind behavior, thread model, and hook ABI.
- Produce a dependency and license inventory before copying or modifying upstream code. Preserve GPL and third-party license obligations.

### P1 — CPU/runtime
- Generate ARM64 AOT code for the game executable and required modules; no x86-64 FEX runtime and no runtime JIT dependency in the iOS target.
- Port the PS4 compatibility runtime (memory, virtual memory, threads, synchronization, files, time, networking/services, audio, video, controller and save data) to iOS-compatible APIs.
- Replace Linux-only syscalls, ELF loader assumptions, dynamic-loader paths, rootfs paths, signals and process-launch behavior.
- Audit executable memory, code signing, page protection and iOS entitlement restrictions. AOT output must be ordinary signed ARM64 code/data, not writable-executable JIT pages.

### P2 — graphics
- Establish a small Vulkan/shadPS4 smoke test on iOS before attempting game rendering.
- Evaluate MoltenVK as a compatibility prototype and enumerate unsupported Vulkan extensions/features.
- In parallel, scope a real Metal backend for the shadPS4 renderer if the Vulkan compatibility route is incomplete or too fragile.
- Validate PS4 GPU command processing, shader translation, descriptor/resource lifetime, fences/semaphores, memory heaps, render targets and drawable presentation independently.

### P3 — Apple platform integration
- SwiftUI launcher and document picker for the user's game dump.
- Sandboxed game-data location using security-scoped URLs and coordinated file access.
- Metal presentation view, orientation/thermal handling, audio session, GameController support (DualSense/Xbox/MFi) and on-screen controls.
- Save data, shader cache, logs, crash diagnostics and export/share support.
- Keep the app foreground-only while gameplay is active; do not promise background gameplay.

### P4 — validation and distribution
- Build a minimal iOS app and run XCTest on the simulator.
- Device build for arm64; simulator success alone is not evidence of GPU/game compatibility.
- First milestones: app launch → Metal clear → runtime library load → AOT smoke test → PS4 module initialization → first frame → audio/input → playable section.
- Package an unsigned IPA in CI; signing requires the user's own Apple signing credentials. Never include a game dump or signing secrets in the repository/artifacts.

## Implemented shell milestone (2026-11-01)

A separate XcodeGen project now lives under `SpartanPort-iOS/`; it does not replace or alter the existing KintTany app target. The app can select a user-owned PS4 game folder, checks `sce_sys/param.sfo` with a bounds-checked PSF parser (title, Title ID, version and category), checks for `eboot.bin`, and inspects the ELF64 little-endian x86-64 header and program-header table bounds without loading the game, and presents a real `MTKView` backed by Metal. XCTest covers a valid ELF64 header, a non-ELF file, an out-of-bounds program-header table, PSF metadata extraction and truncated PSF rejection. The CI workflow builds an unsigned device app and packages it as an IPA artifact. This is a platform-shell milestone only: it does not load the PS4 executable, execute AOT code, translate PS4 GPU commands, or start gameplay. An unsigned IPA is not installable as-is without appropriate signing.

## Immediate blockers

- The documented AOT branch is not present in the currently published upstream branch list; the Android `arm` branch alone uses FEXCore and is not an acceptable native iOS CPU solution.
- No iOS Metal backend for shadPS4 has been verified.
- No iOS-native PS4 system runtime has been verified.
- Therefore a playable IPA cannot honestly be promised until the CPU/AOT and GPU backend blockers are resolved.

## Acceptance rule

Do not label a build “working” merely because Xcode compiles the SwiftUI shell or creates an IPA. A milestone is complete only when its stated runtime/device test passes and its logs/artifacts are retained. The first deliverable is a reproducible iOS shell plus a measured CPU/GPU feasibility result, not a fake launcher that claims to run the game.


## Runtime linker correction (2026-11-01)

The first installed IPA failed at launch with dyld reporting `__simple_mtx_plain_init_once` missing from the flat namespace. Inspection of the run #17 artifact showed this symbol undefined in multiple members of the bare `libkk.a`. Mesa defines it in `src/util/simple_mtx.c`, which is part of the separate `libmesa_util.a`; the C11 mutex implementation is also delivered in a separate archive. The previous Xcode flags allowed undefined dynamic lookup, so the app linked while leaving Mesa-internal references unresolved. The attempted archive merge was not a reliable dependency-closure strategy: Meson had not emitted every static-library target, and the resulting archive left 3,307 symbols unresolved at the Xcode link. The corrected build discovers/builds the full Meson static-library target set and passes each archive to the final Xcode link with `-force_load`, while checking the exact missing symbol families observed in the failing link. It removes `-undefined dynamic_lookup` and excludes the smoke harness from the production executable. The next device IPA must be installed and launched to validate the fix on hardware; a successful CI build alone is not a device-runtime pass.
