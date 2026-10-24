# XOWUE — Native Build 32 correction and limits

Based on actual Build 31 iPhone log and working Xenia Metal capture.

## Critical real guest memory mapping discrepancy

Xenia logs show the first X_MEM_RESERVE of 0x100000 bytes mapping to 0x40000000, with later NtAllocateVirtualMemory results in the 0x40000000 range. The XOWUE baseline instead initialized g_nextVirtualAllocation at 0x10000000 and used the **same counter and allocation vector for GPU-addressable physical allocations and virtual allocations**. This violates the Xbox guest address-space split. The candidate changes:
- Virtual heap: 0x40000000..0x6FFFFFFF, tracked independently.
- Physical heap: 0x10000000..0x1FFFFFFF, separately tracked and bounded.
- Separate reset and physical release bookkeeping.
- NtQueryVirtualMemory starts at the queried page, reports contiguous matching protection/commit range; decommit ranges rounded safely.
- Preserve fail-closed MEM_RELEASE on interior pointers, as required by real kernel semantics. No fake success.
- Xbox root object handles are translated from authorized host root paths back into guest device paths; DOS \\??\\ prefix handled.
- XexGetProcedureAddress unresolved exports recorded explicitly, never an invented AOT function.
- AOT bctrl target=0 records CTR, instruction bytes, preceding eight guest instructions, argument registers, LR and last AOT function. Generated PPC owner source is captured as a GitHub artifact.

## Guest-origin graphics
- A valid offscreen color render target can now enqueue an actual Vulkan image-to-buffer readback after MSAA resolve.
- After vkQueueWaitIdle, the RGBA8 result can be committed to the exact active VdSwap guest framebuffer layout (tiled/linear, endian and swizzle), only if guest fetch descriptor, base, dimensions and format agree.
- Never invent colors, never replace a missing EDRAM color source with a fake image.
- Source color tile 720 was unavailable in the Build 31 trace, so the existing guest command sequence may still present black until the PPC execution proceeds to real color draws.

## Remaining blockers and no promises of gameplay
- CTR-null root cause needs full runtime evidence and source owner; this patch corrects a major memory mapping inconsistency but may expose additional missing AOT/kernel behavior.
- No PPC interpreter/JIT. No synthetic frames. No masking guest crashes.
- Complete native per-tile EDRAM state, depth/stencil sharing, full memexport, timing, and beyond this title's observed shader formats remain unfinished.
- CI success verifies build only; user-provided on-device logs required to prove gameplay frames.
