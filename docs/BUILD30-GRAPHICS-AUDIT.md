# XOWUE — Run 73 (Build 29) native graphics audit

Run #73 is Build 29, commit 415d17f. The working Wolverine gameplay capture in Xenia Metal on Apple A19 Pro shows hundreds of shaders, diverse textures, guest EDRAM/MSAA, resolves and GPU memory synchronization.

## Changes

- Expand native Xenos shader record cap from 256 to 4096; report overflow explicitly.
- Increase maximum native guest draw snapshot count per presentation batch from 64 to 128.
- Reuse up to 512 real Vulkan graphics pipelines keyed by compiled vertex/pixel shaders and topology rather than rebuilding the same pair repeatedly.
- Preserve per-draw Xenos registers for mode, render targets, 2x/4x MSAA settings, depth, blend, scissor and resolve requests, with diagnostic output to expose the missing render target graph.
- Preserve the PPC-to-ARM64 AOT runtime and KosmicKrisp; no guest CPU interpreter, JIT, or simulated framebuffer.

## Not yet implemented

These changes do **not** constitute a complete Metal renderer. XOWUE still lacks a complete native Xenos EDRAM/render-target graph with MSAA resolves to guest memory, full texture format coverage (BC1/3, D24 and FP16), depth-only pipeline support, memexport writes and coherent GPU-to-guest memory readback. The current compositor still uses the host swapchain draw path rather than complete guest EDRAM. Do not claim gameplay rendering without nonblack guest frame evidence on device.

## Test

The XOWUE CI runs GPU wiring smoke tests and builds the IPA. On-device tests must confirm GPU-origin colored pixels and actual frame progression, not merely successful calls to vkCmdDraw.

Extended Xenos tiled guest texture sampling for R8, RG8, RG16, RGB10A2 and RGBA16F. DXT/BC, depth and EDRAM remain unsupported; no fake rendering claim.
