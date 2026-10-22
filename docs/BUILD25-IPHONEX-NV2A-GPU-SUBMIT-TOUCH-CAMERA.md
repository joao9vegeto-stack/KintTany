# Build25 forensic iPhoneOS: actual GPU submit failure + camera touch input

- Actual B24 iPhone 17 Pro 281.4s gameplay video shows real Xbox Prince of Persia 3D at ~53-60 FPS, 16 HUD controls visible, and scene progression into gameplay. No mock rendering.
- Native Build24 trace 1792652744: xbe_entry, real Vulkan GPU init, first composed frame, then Xbox UDATA save-file lookups.
- iPhone LiveContainer-2026-10-22-041019.ips SIGABRT thread #7: abort -> ng_fail -> ng_submit_encoded.cold.3 -> ng_flush_draws -> hw_clear -> nv2a_pb_scan_to -> nv2a_ack_thread. This differs from prior B23 AGX Metal encoder abort.
- Exact Build24 libPoPTSTRetail.dylib disassembly: ng_submit_encoded offset 0x389d4 SDL_SubmitGPUCommandBuffer, returns false -> conditional branch at offset 0x389d8 to cold.3 at 0x1c3c438 -> ng_fail("submit"). It is a real SDL GPU submission failure, not a fault in translated Xbox instructions.
- SDL_GetError reason was only printed to stderr, not iPhone exportable trace; possible device lost, allocation pressure, or other return cannot be distinguished without new diagnostic.

## B25
- In iOS native NV2A, after every 24 SUCCESSFUL GPU submissions call SDL_WaitForGPUIdle and log progress every 240. This bounds in-flight GPU resource lifetime without dropping any Xbox draw, while preserving 48-draw render-pass partition and the existing one swapchain frame.
- Before fail-closed ng_fail abort, export exact SDL error and caller to the native text report. No hiding GPU failures.
- New touch camera response: floating origin (tap begins centered), radial clamp to avoid overdriven diagonals; deadzone 4.5% and smooth exponent 0.86 with adjustable 1.0/1.6/2.2/2.8x sensitivity via top-right CAM button, saved locally. 1.6x default. Left movement maintains linear full-range; sticks slightly larger and ABXY moved inward.
- No changes to shader combiner math or game file content; graphical corruption not claimed fixed. Need on-device tests for long-run crash and camera preference.
- Structural AOT 14,752 definitions audit preserved. Only PoPTST branch, one orphan root commit and one Actions workflow per revision.
