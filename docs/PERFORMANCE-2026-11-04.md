# GoW3 iOS performance and CI handover — 2026-11-04

## Target

- 30 real rendered frames per second at the game's native 1920x1080 scene resolution on iPhone 17 Pro / A19 Pro.
- Do not count frame interpolation as real game simulation/render throughput.
- 60 Hz presentation or frame generation is a separate later target; it must not hide a sub-30 FPS renderer.

## Evidence from this repository's device profiling

The device notes in `docs/NEXT.md` record:

- The main scene pass at 1066x600 took about 24–28 ms with roughly 1,500–2,500 draws.
- At 480p the main pass still took about 27.5 ms; bloom improved, but the main scene did not.
- The notes attribute the heavy-scene limit to per-draw/per-vertex cost (about 11 microseconds per draw), not pixel fill.
- 30 FPS was reached in lighter scenes, but fights above roughly 2,000 draws remained below target.
- Earlier measurements also found that disabling object motion removed about 19 ms of GPU work in a Hades profile. That remains disabled.
- The tested MoltenVK discrete descriptor binding setting and FEX TSO-off settings remain enabled because the repository's A/B notes showed improvements on the tested device.

Therefore the previous 640x360 default was not justified by the measured bottleneck. The iOS default is restored to native scene resolution; scene proxy scaling/adaptive scaling are opt-in diagnostics only. The 30 FPS cap remains a pacing target, not a claim that the GPU can sustain it in every scene.

## Renderer changes retained

`Scheduler::BeginRendering` now keeps a dynamic-rendering instance open when the color/depth attachment views, layouts, dimensions and layer count are unchanged. If only clear metadata changes, it emits `vkCmdClearAttachments` inside the existing rendering instance instead of ending and restarting it.

This is relevant to Apple-family tile GPUs: render-pass load/store actions can move attachment contents between device memory and tile memory. Apple documents that unnecessary loads/stores are costly; the Khronos Vulkan synchronization guidance also warns against over-broad synchronization. The optimization is deliberately limited to identical attachment sets and preserves the requested clear operation.

## Multi-draw research

- `VK_EXT_multi_draw` is designed to reduce repeated driver work for multiple draws with compatible state.
- MoltenVK 1.4.2 (the pinned version used by this project) does not include this extension.
- MoltenVK's 1.4.3 development notes list `VK_EXT_multi_draw`, but the release is still marked TBD in the upstream notes as of this handover.
- Enabling the extension in MoltenVK alone would not accelerate this game: the renderer must also identify adjacent draws with identical pipeline, descriptors, vertex/index bindings and dynamic state, then batch them without changing guest-visible draw order or shader draw semantics. This is a separate renderer-level change and must be validated against GPU captures before shipping.

## CI topology

There is one workflow file: `.github/workflows/ios.yml`.

1. `validate` runs the fast Linux runtime tests.
2. Only after validation succeeds, `ipa` starts on macOS.
3. That single native build compiles FEXCore, the runtime and the GPU library through `native/scripts/build-ios.sh`.
4. The same job then builds the Expo/Xcode app, builds the JIT helper, packages the IPA and uploads logs/artifact.

The former standalone `gpu.yml` and `runtime.yml` workflows are removed. This avoids a separate GPU compile that duplicated the IPA's native build, and a separate iOS runtime compile that duplicated compilation inside the complete native build. Workflow-level concurrency does not cancel an already-running job.

## Device validation required

After installing the IPA, test the same heavy save/scene used by earlier profiles, with the phone cool and no diagnostic GPU profiler enabled for the normal FPS result.

Verify in `Documents/gow3/loader.log`:

- Scene/output remains 1920x1080; no 640x360 proxy rasterization is active by default.
- `GOW3_FRAME_STATS` reports frame-time distribution, not just a cap of 30.
- GPU timing identifies whether the main scene pass, texture streaming/readbacks, or another pass is the limiting factor.
- Thermal-state changes are correlated with frame-time degradation.

For deeper diagnosis, use `GOW3_GPU_PROFILE=3` only for a short capture (it changes pass recording and costs FPS), and use Xcode Instruments' Game Performance template / Metal System Trace on a physical device. CI can prove compilation and tests; it cannot prove sustained 30 FPS on the phone.

## External technical references

- Apple, Setting load and store actions: https://developer.apple.com/documentation/metal/setting-load-and-store-actions/
- Apple, tile-based deferred rendering: https://developer.apple.com/documentation/metal/tailor-your-apps-for-apple-gpus-and-tile-based-deferred-rendering
- Apple, Metal app performance profiling: https://developer.apple.com/documentation/xcode/analyzing-the-performance-of-your-metal-app/
- Khronos, Vulkan synchronization examples: https://github.com/KhronosGroup/Vulkan-Docs/wiki/Synchronization-Examples
- Khronos, VK_EXT_multi_draw: https://docs.vulkan.org/refpages/latest/refpages/source/VK_EXT_multi_draw.html
- MoltenVK, release notes and configuration: https://github.com/KhronosGroup/MoltenVK/blob/main/Docs/Whats_New.md
