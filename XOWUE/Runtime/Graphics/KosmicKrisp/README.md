# KosmicKrisp iOS Metal WSI reference for XOWUE

This folder pins and preserves the iOS port work from the same repository's `PsTJohn` branch, latest source commit:

- PsTJohn commit: `db014165eb39429ae37d1946db6fc83c600c63b3`
- Mesa/KosmicKrisp: `bfe063f723d436e5cdef8a98f058d4e44a64810c`
- Patch 0001: iOS platform, Metal 4 device path, iOS Mach VM aliases.
- Patch 0002: `VK_EXT_metal_surface`, `CAMetalLayer` WSI and iOS guards.
- Patch 0003 and `smoke/kk_ios_smoke.m`: optional standalone iOS clear/present smoke target from M3B.

## What it provides

The patch set adapts the KosmicKrisp Mesa Vulkan driver to iOS Metal surfaces. The smoke app creates a Vulkan instance, Metal surface, swapchain and clear/present loop. That verifies only the driver/WSI path.

## What XOWUE still needs

This is not a Xenos graphics implementation. XOWUE does not yet link this Mesa build. Before it can display the game, it needs:

1. An Xenos/D3D command processor and state decoder.
2. Shader translation from Xbox shaders to a format accepted by the Vulkan driver.
3. Xenos tiled texture/render-target formats, resolve/copy paths and guest GPU memory tracking.
4. Command submission and synchronization integrated with XOWUE's PPC runtime.
5. A real iOS app-owned `CAMetalLayer` and linking/loading of the built KosmicKrisp ICD.

The app currently reports this accurately as a pinned backend reference, not an active renderer. No XOWUE game frame has been produced.

## Provenance

Patch sources and smoke harness come from `joao9vegeto-stack/KintTany`, branch `PsTJohn`, commit `db014165eb39429ae37d1946db6fc83c600c63b3`. Apply them only to the pinned Mesa commit above. Preserve Mesa's per-component upstream license notices if Mesa sources or binaries are later included.
