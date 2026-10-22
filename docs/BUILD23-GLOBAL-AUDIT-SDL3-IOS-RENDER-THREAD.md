# PoPTST Build 23 - global structural audit and first real graphics thread fix

## Proof from Build 22 native iPhone crash (LiveContainer-2026-10-22-022526.ips)
SIGABRT -> objc_exception_throw -> NSAssertionHandler -> UIView removeFromSuperview -> SDL_uikitview setSDLWindow: -> UIKit_Metal_CreateView -> UIKit_Vulkan_CreateSurface -> VULKAN_ClaimWindow -> hw_active -> nv2a_ack_thread.
The guest advanced beyond Build21 0x808E8014 KERN_PROTECTION_FAILURE and its B22 logs confirm seven GPU PAGE requests were restored RW successfully. No game frame rendered yet.
**SDL3 3.4.18** public SDL_gpu.h specifies SDL_ClaimWindowForGPUDevice MUST run on the thread that created the SDL_Window. PoPTST creates the window on UIKit main thread inside poptst_engine_start; rePOP native GPU lazy initialization calls the claim from NV2A ack worker. This violates both SDL's contract and UIKit's view hierarchy rule.

## Fix class (rather than skip exception)
- iOS host provides synchronous main-queue claim/release callbacks using dispatch_sync_f plus a direct branch when already on main.
- rePOP native Vulkan GPU device, shaders, command buffers, game x86->C->ARM64 and NV2A executor remain on the owning worker. Only window/swapchain ownership lifecycle is serialized on original SDL UIKit thread.
- On iOS the NV2A backend is explicitly forbidden to SDL_DestroyWindow it does not own (already patched in prior build); source regression test verifies.
- Host records actual claim success/failure, renderer ready, and FIRST REAL NV2A COMPOSED SWAPCHAIN FRAME SUBMITTED strictly after non-null swap and ng_submit. Do not equate SDL window creation or GPU initialization with a game frame.
- Android and Windows SDL_GPU operations are retained without intercepting them.

## Full AOT static audit
Run ios/Tools/audit_full_retail_aot.py against all retail generated C units AFTER iOS patch, 294 candidate mid-entry repairs and 39 fail-closed stubs. It reconciles header declarations, every C definition, dispatch VA, ABI call sites, labels, unimplemented instruction sites, fatal stub guards and double-defined functions. Outputs reports/aot-full-audit.json, archived by Actions.
Structural integrity cannot prove x86 semantic equivalence, dynamic coverage or rendered scenes. Passing CI does not prove a game menu.

## Evidence gates for iPhone
Stage 1 GPU B23 SDL window claimed + Metal/Vulkan surface created ON MAIN.
Stage 2 GPU B23 native NV2A renderer initialized.
Stage 3 GPU B23 FIRST REAL NV2A COMPOSED SWAPCHAIN FRAME SUBMITTED.
If a stage fails, use new native trace and .ips, not guesses. User still needs to run signed IPA on an actual iPhone 17 Pro.

## Scope discipline
Only branch PoPTST root orphan commit. Single push and workflow per revision. No game assets, xbe, license, or user data committed. rePOP remains pinned.

## Build23.1 full-AOT audit correction (NOT a runtime hotfix)
Actions #32 identified 15 dispatch targets not defined in gen/*.c. Inspection proved these 15 are real hand-written retail function definitions in source/xbox-retail/target_hooks.c, linked by the same iOS CMake target. The verifier now includes target_hooks.c as an explicit category, rather than inventing missing code. The 8 extra unimplemented-opcode callsites are duplicated in generated mid-entry clones; original unique x86 opcode site count remains 725. This removes false-positive coverage errors while keeping unresolved stubs and actual ABI gaps visible. Runtime/UI fix remains identical to B23.

## B23.2 preflight source correction
Pinned recomp_funcs.h declares 15 linked title-hook entry functions with a trailing C annotation (example: void sub_0001E970(void);  /* retail hook */). The AOT verifier must match a semicolon followed by optional annotations, not insist on a line ending immediately after the semicolon. The full reference header yields 14,752 declarations including these 15. No runtime change; prevents a false structural mismatch.

## B23.3: complete SDL3 UI getters threading audit
SDL3 3.4.18 SDL_video.h marks SDL_GetWindowSizeInPixels and SDL_GetWindowFlags main-thread-only too. Those occur from rePOP ng_compose / ng_present on the NV2A worker every frame. For iOS, the host now captures both values only on UIKit's main thread in the existing SwiftUI pump and atomically publishes them to the GPU worker. Avoids expensive per-frame dispatch_sync_f and incidental UIKit cross-thread reads. Native GPU present mode checks/submissions remain on the worker and Android/Windows retain original SDL calls.
