# Build 141 — Xenos packed constant upload matches shader translation

## Concrete Build 140 failure

Build 140's visible startup image turns green/corrupt during the Marvel logo. The log records the video pixel shader 50088B75BDAA1827 and vertex shader B458DC9522932E55 being translated, linked and submitted, with texture mask 0x7. Draws were not rejected by the Vulkan path. That proves submission, not correct color output.

The concrete source-level contract mismatch is:

1. shader_translator.cpp::Const marks absolute c-register reads (index < 256) in TranslatedShader.constUsed and rewrites generated GLSL to use a compacted c-slot.
2. PackedConstantsEnabled() enables that optimization by default unless NFSMW_CP_OPT explicitly clears bit 8.
3. Before this fix, XOWUEGpuBridge.cpp::ShaderRecord discarded both constPacked and constUsed; QueueDraw therefore placed no per-stage packing metadata in the draw packet.
4. XOWUENativeDraw.inc uploaded all 2296 raw dwords unchanged while XDPush still selected vsConstBase=0 and psConstBase=256.

Thus GLSL's rewritten indices and the UBO's source-register layout could disagree. A color-conversion shader can then read unrelated constants for YUV matrices/offsets, producing a green or otherwise corrupted frame even when its Vulkan draw succeeds.

## Correction

- Carry constPacked and the 256-bit used-register mask independently for vertex and pixel shaders through ShaderRecord and XOWUEGuestDraw.
- Pack each stage's actual float4 constants in ascending source-register order exactly as the translator remapped them.
- Leave non-packed/relative-addressed shader constants byte-for-byte unchanged.
- Keep the fetch constants, boolean constants, loop constants and reserved tail at their original offsets (starting at dword 2048).
- Run a native C11 smoke test for both stages, register ordering, fetch-tail preservation, non-packed behavior and invalid arguments before the iOS build.

This fixes a real translator/uploader mismatch in the renderer path; it does not fabricate pixels or replace the title's Bink decoder.

## Still-open menu handoff

The Build 140 log independently shows the main PPC thread repeatedly polling the stream-manager callback at 0x82575250 from the 0x82575510 callsite. The callback eventually returns zero and the main thread remains in that guest loop. Successful reads of .bik files do not prove completion of the game's final stream request. This commit deliberately does not force a guest return, skip the movie, or claim that the menu issue is solved; it addresses the confirmed color-constant mismatch first.

## Regression acceptance

CI must pass the constant-packing C smoke test, existing Xenos shader/PM4 contracts, and the full macOS 26 iOS IPA build. Device acceptance still requires the Marvel/FOX/UE3 logos to retain correct colors and the title to reach an interactive menu; an IPA build alone is not sufficient.
