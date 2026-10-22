# PoPTST B27: 0.75x camera, verified native-save backups and genuine process exit

Evidence from user's Build26 2026-10-22 crash diagnostic:
- REAL AOT entry 0x00335753 at timestamp 1792681959.885. NV2A Metal/Vulkan first presented frame 1792681960.112. Many command submissions into 1792682427, no fatal signal reported in this file.
- EXIT tapped at 1792682401.843; diagnostic says guest active; GPU continues submitting 34,000+ more commands afterwards. Returning to launcher DID NOT terminate guest — unambiguous.
- Video and screenshots show gameplay and working RES 480/720/1080 and CAM level cycling.
- B26's camera defaults used old V1 preference key on install but saved to V2 on change, preventing persistence.

B27 actual changes:
1. A fifth camera level 0.75x in list 0.5 / 0.75 / 1.0 / 1.5 / 2.0. Always passes percent (75) into rePOP's *actual lifted guest camera hook* path `sub_000DBDE0 -> resot_scale_look -> resot_look_value`; title code clamps 25..200 percent. Swift/ObjC preference key V3 used consistently; B26 persistence bug corrected; display uses 2 significant figures so 0.75 is visible.
2. Explicit native SAVE BACKUP control on HUD backs up existing Xbox retail save files under userdata/saves/xbox-retail to userdata/backups/native-save-slot, rollback to previous on failed move. Rejects empty saves and explains need to first save at an actual game save point.
3. Launcher "RESTaurar save do jogo e iniciar" backs up current active saves to before-restore, restores that native backup, then boots the original retail game. User selects the game's own LOAD/CONTINUE menu. This is native disk save-file recovery, NOT exact CPU/PPU/GPU savestate. Never claim exact frame restoration.
4. EXIT now opens confirmation alert and calls `poptst_engine_exit_to_launcher`, which logs, fsyncs trace fd, and `_exit(0)` terminates entire app process. Guest cannot continue rendering unseen. It does NOT return to the SwiftUI launcher: user must relaunch PoPTST/LiveContainer. This is deliberate: suspended active native guest, NV2A GPU workers, multiple retained locks and iOS no safe guest-only teardown available at present. An abort/async pthread_cancel while inside Vulkan/guest locks is unsafe.
5. All 74 retail AOT units, rePOP pinned source, Vulkan/KosmicKrisp code and render options unchanged. Branch PoPTST only, one orphan root commit, one workflow.

Acceptance criteria:
- The CAM button shows CAM 0.75× and after relaunch restores that exact setting, and changes the game's internal camera multiplier (check gameplay, some camera modes locked by title).
- Press BACKUP after native save: files actually copied; restore at launcher copies into active game saves before boot, load from title menu. If no native save files exist, display not available instead of falsely claiming saved.
- EXIT confirms and stops all threads and app process. User can re-open, not click play in same terminated process.
- Instantaneous savestate: NOT implemented. To implement exact instruction/memory/Vulkan state, one would need coordinated suspension and serialization/reconstruction of ARM64 TLS and guest x86 registers, PSH buffers and guest GPU state, APU, host objects and thread scheduling; RAM-only snapshot is insufficient and dangerous. Do not offer an inexact savestate as if completed.
- Existing remaining graphical issues, crash validation and screenshot comparisons require on-device test.
