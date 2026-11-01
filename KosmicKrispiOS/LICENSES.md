# Third-party notices

- Mesa/KosmicKrisp source is fetched from https://gitlab.freedesktop.org/mesa/mesa at commit `bfe063f723d436e5cdef8a98f058d4e44a64810c`. Preserve the complete LICENSE and per-file notices from that exact checkout when redistributing source or binaries. The included patches do not relicense Mesa.
- SPIRV-LLVM-Translator is fetched from https://github.com/KhronosGroup/SPIRV-LLVM-Translator at commit `e328468fd329342f1f60c12fdd19cc0faaa88f32`; review and include its Apache-2.0 license and notices.
- Vulkan headers are copied from the pinned Mesa tree; preserve Khronos copyright/license headers.
- The dynamic bridge is adapted from the PoPTST integration and marked MIT in its source. The static bridge/probe are integration glue and MIT-licensed.
- For redistribution, include the upstream license texts from the exact fetched revisions, the generated build manifest and SHA-256 hashes. This folder is not a blanket license grant for dependencies.
