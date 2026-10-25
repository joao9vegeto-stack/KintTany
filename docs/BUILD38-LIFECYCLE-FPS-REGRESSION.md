# XOWUE Build 38 — lifecycle cancellation and FPS HUD regression

Build 37 was reported frozen at the Wolverine title screen. This patch does not claim that the game has reached the menu or gameplay; those states require fresh guest frames and an on-device capture.

## Confirmed code defects corrected
- xowue_request_stop() no longer returns early when AOT telemetry is inactive. A user-requested shutdown always wakes guest waiters and requests cooperative PPC scheduler stop.
- SwiftUI no longer allows a transient isBusy state to convert SAIR during the booting phase into a view-only dismissal.
- The single existing real-FPS label remains based on newly decoded guest frames, not repeated host presentations. Its layout is anchored to the game viewport at a fixed inset, away from the outer SAIR/branding HUD.
- tools/test_xowue_gpu_wiring.py now checks these invariants in CI.

## Important runtime limitation
The previous evidence showed PPC activity but stalled guest Xenos draw/swap progress after a small initial number of frames. This commit fixes verified lifecycle/UI defects; it does not fabricate missing movie assets, substitute host presentation rate for game FPS, or claim the guest title transition is repaired without a new runtime trace proving new guest draws/swaps.
