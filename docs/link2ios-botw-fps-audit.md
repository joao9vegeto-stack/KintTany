# Link2iOS BOTW — FPS/frame-step audit (2026-11-11)

## Device-log facts

The uploaded iPhone 17 Pro log starts with:

- \`DM_FPS_TARGET=60\`
- \`DM_FPS_HOLD=on\`
- \`DM_PRESENT_SNAP=1\`
- \`DM_NVN_ENC_THREAD=1\`
- \`DM_OPMODE=0\` (Handheld)
- \`DM_RENDER_SCALE=0.5\` in that particular test session
- A 60 Hz display, a present-snapshot ring of two host textures, and Metal encoding on its own thread.

The profile summary's \`enc_thread 0\` is the stored profile value; it does not contradict the logged \`DM_NVN_ENC_THREAD=1\`. The upstream iOS setting defaults the encode thread to \`1|DM_GAME_ENC_THREAD\`. BOTW's game profile already enables \`present_snap\`.

The pinned engine is already based on the corrected fast-wake/segment-publication implementation (upstream commits \`60625182\` and \`06b7b3e\`). That path includes the completion-order lock and the shared finite SyncWait timeout budget. The snapshots+encode-thread+fast-wake combination is therefore already present; it is not being blindly re-added.

## What actually forces 30 FPS

The log does not show the game fixing its own frame step. Instead, the host frame-step controller repeatedly logs a hold increase from one to two VSyncs after three late frames, then probes to return to one. The loaded device log records 64 frame-step transitions and many failed recovery probes.

The first hold increase occurs while total frame cost has exceeded the one-VSync budget; subsequent windows show higher GPU time while the longer hold is active. This creates a feedback pattern: holding for 2/3 VSyncs reduces work/activity, the GPU clock falls, and the later 60 Hz probes are less likely to pass.

Thermal state starts at 0 and later reaches 1 (Fair); this log does not show Serious/Critical thermal state. The hard thermal/movie caps remain separate.

## Correction

Set BOTW's \`fps_hold=off\` in both the generated game profile and the runtime \`profile.tsv\`, while preserving:

- \`fps_target=60\`
- \`present_snap=on\`
- \`enc_thread=on\`
- \`op_mode=handheld\`
- the existing \`present_interval=game\` behavior
- the user's render-scale value (no render-scale or resolution edits)
- the previous optimized IPA's guest modules, RomFS/AOC, Metal libraries and pipeline archive.

With hold disabled, the host no longer extends a late 60 Hz frame to two or three VSyncs. A frame that cannot meet 16.67 ms may still be missed; the goal is to avoid forcing the entire presentation cadence down to 30. The serious-thermal and movie caps remain active.

The speculative \`draw_barriers=game\` experiment is removed; the upstream BOTW notes report no gain from that mode.

## Present snapshots + encode thread audit

| Item | Verified state |
|---|---|
| BOTW \`present_snap\` game profile | \`on\` |
| Device \`DM_PRESENT_SNAP\` | \`1\` |
| Snapshot ring | 2 host textures |
| iOS encode-thread default | \`1|DM_GAME_ENC_THREAD\` |
| Device \`DM_NVN_ENC_THREAD\` | \`1\` |
| Encode-thread own-record copy path | present |
| Corrected fast-wake completion path | present in pinned engine |
| Resolution / shader / texture quality | untouched |

## Build and device verification

The optimizer selects the newest successful optimized IPA artifact from the previous run, excluding run #6; it never falls back to the original/base IPA. It rebuilds only the host framework and preserves guest modules verbatim.

The build refuses to publish unless the generated header has \`DM_GAME_FPS_TARGET 60\`, \`DM_GAME_FPS_HOLD 0\`, \`DM_GAME_PRESENT_SNAP 1\`, \`DM_GAME_ENC_THREAD 1\` and Handheld mode, and the final IPA's \`profile.tsv\` has matching values.

After installation, the decisive device-log checks are \`boot: DM_FPS_HOLD=off\`, \`boot: DM_PRESENT_SNAP=1\`, \`boot: DM_NVN_ENC_THREAD=1\`, no normal-gameplay \`hold 1 → 2\`, and frame-step summaries showing one VSync. The 60 FPS goal is not claimed as measured until the next device run confirms it.
