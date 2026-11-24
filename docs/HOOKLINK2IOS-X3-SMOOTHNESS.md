# X3 smoothness pass (2026-11-24)

Device log confirms recovery of 278f48371bcf0d58_b; 9.57 s preparation, 13.0 fps in frame 901–1200, 42.97 ms GPU median, 432 texture heaps made / 0 reused / 314 freed, 2.38 GB advised preread. No fatal signal in captured session. Thermal state 2 before gameplay; fixed 0.85 scale means 1635x920 vs earlier dynamic 1280x720. Comparisons are not controlled A/B.

Changes: direct use of the known successful full compute variant only for the verified shader, retaining fallback; retired heaps under memory pressure may stay at most 350 ms and 32 MiB only with >=1536 MiB available; otherwise immediate trim. Preread actual page hashing and 128 MiB pending budget; skipped advice never marks range seen. GPU occlusion remains OFF by default; experimental path now checks slot and indirect-argument bounds and flushes before publishing job buffer. No claim that GPU occlusion or shader appearance is fixed. The original X3 shader image and guest code are unchanged. Restore dynamic resolution in preset; saved user settings may override defaults. Verify on iPhone before claiming performance improvement.

Build only the native host via existing X3 recovery workflow. Source anchors checked against exact pinned upstream and previous recovery patch. No device or Metal GPU test performed before commit.
