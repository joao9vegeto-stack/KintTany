# SpartanPort for iOS — engineering baseline

Status: SpartanPort iOS shell loads the exact arm64 `libKosmicKrisp.dylib` already consumed by PoPTST from the successful PsTJohn run #125 artifact (commit `db014165eb39429ae37d1946db6fc83c600c63b3`, SHA-256 `593d3f39a4fc751cc51884383444a5599993012281e084ef01945db7a4e78a34`). The app resolves `vk_icdGetInstanceProcAddr` with `dlopen`/`dlsym`; CI validates the provider hash, iOS platform, architecture and bundle placement. `KosmicKrispiOS/` remains an optional SDK/build workspace; SpartanPort no longer rebuilds and statically relinks Mesa on every app build. CI publishes the SpartanPort IPA and PS4 AOT compatibility audit. No playable PS4 runtime is claimed; game-start remains disabled.

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

## Source-level review pinned to the currently published upstream `arm` commit `56e804d1ef3e108257b94c51b6f7fb204930a244`

- `cpu/guest_cpu_fex.cpp` creates FEXCore contexts and uses its JIT/code-cache plus Linux signal/ucontext facilities. The published ARM64 branch is not a native AOT CPU implementation.
- `cpu/gportcpu.cmake` links `FEXCore`, `Common`, `JemallocLibs` and `fmt`; it produces `libgportcpu.so`.
- `gpu/CMakeLists.txt` requires Vulkan, SDL3 and X11 on non-Windows builds, in addition to shadPS4 renderer/recompiler and shader tooling. This is not an iOS Metal backend and cannot be assumed to compile unchanged for iOS.
- `src/runtime_memory.c` reserves a large PS4 guest virtual-address range and uses platform-specific mappings. The POSIX path relies on `mmap`/`mprotect`; the Windows path has a separate placeholder/section implementation. iOS address-space placement, executable mappings and memory pressure need a dedicated design and device tests.
- The upstream ARM64 CPU adapter is GPL-2.0-or-later. No upstream source has been copied into this iOS shell; license compatibility and notices must be resolved before importing runtime code.

## KosmicKrisp backend reused from PsTJohn

The graphics provider is the user's existing KosmicKrisp/Mesa port from `PsTJohn`, not a replacement MoltenVK backend. The integration follows the exact proven path already used by PoPTST: download the successful PsTJohn run #125 artifact (`39067594955`), extract `Payload/RPCS3.app/Frameworks/libKosmicKrisp.dylib`, and verify its pinned SHA-256 before embedding it in `SpartanPort.app/Frameworks`. PoPTST's workflow performs the same extraction and checks the same digest. SpartanPort loads the provider with `dlopen` and resolves `vk_icdGetInstanceProcAddr` with `dlsym`; it does not statically relink Mesa's internal dispatch archives into the app executable.

This is a deliberate correction to the failed SpartanPort run #104 static-link path. That link failed with 2,824 unresolved symbols reported from Mesa's generated `wsi_common_entrypoints.c.o`; the generated `-u` extraction list contained 568 defined symbols but none of those unresolved names. The static-link experiment therefore did not establish a closed link dependency graph. Reusing the exact dylib that PoPTST already consumes removes that unsupported static-link assumption and keeps the backend binary reproducible. The optional source build and static/dynamic adapters remain in `KosmicKrispiOS/` for SDK development, not as a prerequisite of the SpartanPort app workflow.

The probe only checks ICD loading and instance extensions. It does not create a Metal surface/swapchain or render a PS4 frame. Physical-device surface/swapchain presentation remains pending, and KosmicKrisp is only the Vulkan/Metal backend—not a PS4 renderer or CPU runtime.

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

The first installed IPA failed at launch with dyld reporting `__simple_mtx_plain_init_once` missing from the flat namespace. Inspection of the run #17 artifact showed this symbol undefined in multiple members of the bare `libkk.a`. Mesa defines it in `src/util/simple_mtx.c`, which is part of the separate `libmesa_util.a`; the C11 mutex implementation is also delivered in a separate archive. The previous Xcode flags allowed undefined dynamic lookup, so the app linked while leaving Mesa-internal references unresolved. The build now merges all iOS static dependency archives produced under `build-ios` into the single SDK archive, verifies the Mesa mutex and C11 thread implementations are present, and removes `-undefined dynamic_lookup` from the app link. The next device IPA must be installed and launched to validate the fix on hardware; a successful CI build alone is not a device-runtime pass.


## Launcher integration milestone (2026-11-02)

The launcher creates Documents/SpartanPort/Jogos, scans the app Documents directory and nested folders for eboot.bin plus sce_sys/param.sfo, displays detected installations, and restores the selected relative path from UserDefaults. The folder picker coordinates access to external Files/iCloud providers and copies the selected game directory into the app sandbox so the selection does not depend on a temporary security-scoped URL. Import runs off the main thread. Documents/diagnostico.txt records detection and validation state; Documents/crash.txt records import/picker errors. File Sharing and in-place document access are enabled so diagnostics and the managed game folder can be inspected in Files.

This milestone implements launcher/storage only. Play remains disabled because this branch still has no PS4 SELF/ELF loader, x86-64-to-ARM64 AOT output, PS4 system services, or PS4 command renderer. KosmicKrisp's separate M3B smoke harness exercises a Vulkan/Metal clear and swapchain path; it is not a PS4 game renderer and is not evidence of God of War III gameplay.

## CI failure audit — runs #78–#80 (2026-11-02)

- Run #78 (`41521416660`, commit `a03efa3f82aa847dead4856def07bf3244314a20`) passed the Ubuntu source/Mesa-patch preflight and failed in the KosmicKrisp Objective-C build before XcodeGen, XCTest, the device build or IPA packaging. The exact compiler error was `Metal/MTL4ArgumentTable.h file not found`; the compiler diagnostics identify `Xcode_16.4.app` and `iPhoneOS18.5.sdk`. This is an SDK/toolchain mismatch, not a Mesa patch-application failure.
- Run #79 (`41523335488`) was cancelled.
- Run #80 (`41523418021`, commit `94f60aa351cc643333911aeaa4a3767256305481`) was cancelled after the preflight job completed successfully. Its macOS build job was cancelled before any build step ran. It did not reproduce or resolve the #78 compiler failure and produced no IPA.
- The workflow now targets `macos-26`, selects an installed Xcode 26 explicitly, verifies the iPhoneOS SDK major version, and compiles a tiny Objective-C probe that imports `Metal/MTL4ArgumentTable.h` before Homebrew dependency installation or the full Mesa build. This turns the exact #78 SDK requirement into an early, cheap gate.
- This pipeline correction does not add a PS4 runtime, AOT compiler, SELF loader or shadPS4 renderer. A successful IPA build remains only an app-shell/backend-link milestone.

## Upstream ARM64 source status — verified against branch head

The published `zFitness/gow3_android:arm` branch currently points to `56e804d1ef3e108257b94c51b6f7fb204930a244`. Its README describes the Android port as FEXCore guest execution plus shadPS4/Vulkan; its AOT section describes a separate experimental `feature/aot-native-arm64` line, but that branch is absent from the repository's published branch list. The documented AOT claims are therefore design/status notes, not a source tree that this iOS project can fetch or build today.

The Android `arm` branch is not an iOS-native execution solution: its packaging contract assumes nixport/rootfs, its CPU adapter uses FEXCore, and its graphics path depends on shadPS4/Vulkan. Reusing its PS4 runtime and loader logic requires an explicit iOS platform layer; copying its Android packaging, Linux process model or FEX JIT path is not an acceptable substitute for ARM64-native execution. No upstream runtime source is claimed as integrated until it is imported with pinned revisions, license notices and iOS-specific build/tests.


## SELF/ELF parser milestone — 2026-11-02

The supplied eboot.bin begins with PS4 SELF magic 4F 15 3D 1D. Its metadata table is followed at offset 0x120 by an ELF64 little-endian x86-64 header. The ELF reports PS4 executable type 0xFE10 (SCE_EXEC), entry point 0x144060 and ten program headers. The inspector now recognizes PS4 SELF and generic SCE SELF magic, validates the SELF header and all eight segment-table file ranges, reads encryption/compression flags, locates the embedded ELF after the segment table, recognizes ET_SCE_DYNEXEC, and validates the program-header table. The supplied file's eight entries declare zero encrypted and zero compressed segments; three entries advertise block metadata. The app now reconstructs an ordinary ELF image from the plaintext SELF entries: it maps PT_LOAD data and the standalone SCE dynamic-data/comment/version segments, while recognizing nested program-header ranges already covered by those segments.

The reconstructed file is written automatically to Documents/SpartanPort/Prepared/<TitleID>/eboot.elf. The reconstruction refuses SELF entries marked encrypted or compressed; it does not attempt cryptography or decompression. The output remains x86-64: this step does not relocate PS4 imports, generate ARM64 code, resolve PS4 libraries or execute the game. The original user-provided eboot.bin is never modified. A structurally valid ELF header does not prove the SELF payload is loadable. Synthetic XCTest fixtures cover SELF and ELF parsing without placing game data in the repository.

The next blocking work remains: verify the exact SELF segment encryption/compression state, obtain the actual AOT compiler source (the documented experimental upstream branch is not currently published), port PS4 system services to iOS, and integrate a working PS4 command renderer over Metal. Play remains disabled until those components are real and tested on physical hardware.


## CI audit — run #82 (2026-11-02)

Run #82 passed the Ubuntu preflight, selected Xcode 26, and compiled all 434 KosmicKrisp static targets. It then stopped in a shell audit that required the generated command-dispatch archive's _kk_AcquireNextImageKHR reference to be weak. The pinned generated table emitted a binding that did not satisfy that overly strict audit, so XcodeGen, XCTest and IPA packaging were skipped. The audit no longer assumes that the optional generated thunk must be present in that archive; if another object requires it, the final iOS link resolves it, and that link deliberately has no -undefined dynamic_lookup escape hatch. This removes the premature gate; it does not claim that the subsequent app link or runtime has passed.


## SpartanPort KosmicKrisp link failure correction — 2026-11-03

Run #104 (`41567466715`, commit `db52913edc4294c3a4742c4caa6b42fe51e4643a`) passed the Mesa/KosmicKrisp source build, XcodeGen and simulator tests, then failed only at the final device link. The linker reported 2,824 undefined symbols from Mesa's generated `wsi_common_entrypoints.c.o`. The `-u` list contained 568 symbols selected from archive definitions and had zero overlap with the unresolved-symbol list; increasing or renaming that force-extraction list could not close the missing dependency graph.

The replacement integration pins the already-consumed PsTJohn dylib by its exact SHA-256, validates arm64/iOS Mach-O metadata before app compilation, and loads it through the same `dlopen`/ICD-entrypoint pattern used by PoPTST. The app bundle must contain `Frameworks/libKosmicKrisp.dylib`; the app executable must not have a duplicate static or dynamic Vulkan link dependency. This correction validates packaging and ICD discovery only; physical-device presentation and PS4 gameplay remain separate milestones.


## iOS ARM64 strict CPU dispatcher port (2026-11-03)

The native AOT workflow now additionally cross-compiles the upstream
`bloodborne-recomp` CPU dispatcher for the iOS 17.4 ARM64 SDK. It builds
Zycore and Zydis for the iOS target (not the macOS host), then compiles the
pinned CPU sources with the exact `GOW3_AOT_ONLY` policy patch used by
`gow3-macos-arm64`.

The iOS CPU archive deliberately excludes `jit_arm64.c`. The patch removes
the JIT dispatcher call and turns uncovered guest instructions/functions into
fatal coverage errors; this is not an interpreter fallback. The build checks
for the required dispatcher exports and rejects JIT symbols. The archive and
its manifest are retained as CI artifacts.

This is the first compiled iOS CPU-runtime component, not a claim of a
playable port. The archive still requires a reviewed iOS host bridge for
`runtime_low_map`, a complete PS4 module/relocation/import loader, the PS4
HLE services, audio/input/filesystem integration, and a working shadPS4 GNM
renderer/presenter. Until those pieces are linked into the app and exercised
on device, game start remains disabled. Zydis and Zycore are external static
link dependencies and are built for the same iOS ARM64 target in CI.
