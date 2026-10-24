# XOWUE Build 31 — native render and AOT findings

Based on the user-submitted video / Build 30 diagnostics and the working Xenia Metal gameplay trace.

## Confirmed blockers

- AOT 148503 calls / 6972 distinct functions, then NULL PPC indirect target 0x00000000; LR 0x82361BF8, last AOT 0x82C450B8.
- Invalid NtFree MEM_RELEASE interior pointer errors are genuine errors according to Xenia's BaseHeap::Release. Do not fake success.
- NtCreateFile rejected object attributes repeatedly. Handle null ObjectName relative to valid root, and trace other arguments.
- 26 guest draws, 2 swaps, GPU scan of 3162132 pixels completely black.
- Xenos mode 5 is depth-only. Mode 6 is guest EDRAM copy/resolve, not a normal triangle draw.

## Implemented in this commit, native-only

- DXT1/DXT3/DXT5 = BC1/BC2/BC3 guest texture decoding, including Xenos tiled and endian handling; standalone smoke test.
- Genuine Vulkan offscreen guest color/depth images keyed by EDRAM tile, pitch, surface format and sample count, supporting 1x/2x/4x framebuffer samples where supported.
- Native depth-only vertex pipeline without a fragment color shader.
- Native vkCmdResolveImage for guest color EDRAM MSAA, followed by rendering to the host swapchain; no fake pixels.
- PM4 copy packets may be queued without guest VS/PS. Copy destination registers retained for further guest memory integration.
- Explicit swapchain layout transitions and Vulkan pipeline caching keyed by render pass and samples.
- Null native PPC callsite byte capture at LR-4 and PPC arguments r3-r10; strict AOT-only execution retained.

## Remaining unimplemented requirements — no false claim

Guest physical tiled writeback of color resolves is NOT yet wired to the original Xbox memory; CPU/GPU guest coherency, complete guest EDRAM color/depth sharing, persistent MSAA depth/stencil, full Xenos texture format matrix and pixel memexport remain incomplete.
The Build 30 null PPC indirect dispatch is not cured by fabricated fallback targets; actual guest callsite bytes are required to verify the root cause.
An iOS Actions success proves compilation, not correct Wolverine gameplay.

## Required on-device acceptance evidence

Game advances beyond former null PPC target; native EDRAM color/depth surfaces allocate; real guest shaders produce nonblack GPU readback; multiple distinct game frames / proper landscape presentation; no host-only frame duplication.