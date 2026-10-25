# XOWUE Build 37 — user-observed graphics stall, lifecycle and UI

## Build 36 iPhone evidence (diagnostico-build-36.txt; screen recording)
- Native PPC remained running. No AOT slot failure, panic or firmware return appears in the supplied trace.
- Guest execution reached at least 8,192,000 AOT entries and ~12,636 distinct AOT functions.
- Genuine GPU rendering reached 54 submitted Xenos draws, 5 guest swaps, 2 composite frames and
  2,207,982 nonblack pixels in the previous full-resolution readback.
- Metal kept displaying the *same* image: 2,460 host presents with only 5 distinct decoded guest
  frames and no further draws. These are not 2,460 game frames, hence a frozen guest is 0 FPS.
- Original Xbox game uses 1280x720 (16:9); host surface reported 2622x1206 (2.17:1).
- User exit dismissed UIKit but left native PPC threads running until a separate runtime return.
- Missing NT guest files: D:\WGame\Movies\Copyright.txt, ravenlogo.xxx, blank.bik,
  UE3_logo.xxx, FOX_LOGO.xxx, MARVEL_INTRO.xxx, ATVI_logo.xxx (0xC0000034).
  Such failures may be missing game files or path layout; do not manufacture dummy videos.
- Official Xenia compatibility issue 1153 independently reports Wolverine transitions from logo to
  menu can stall; this does not establish the same cause for this native iOS port.

## Build 37 changes
1. Export a real cooperative C ABI to stop PPC scheduler and all guest threads. Swift SAIR button
   requests cancellation and waits for xowue_boot_xex to return before dismissing. Outcome 4
   marks *intentional* stopped session, not firmware failure. Also cancel on unexpected disappear.
2. Present Vulkan/Metal native UIView at 16:9 fit with true black side letterboxes on iPhone.
   The game render surface can resize independently of the control overlay.
3. Reorganize touch clusters at bottom left/right, center Start/Back/visibility controls, replace
   BIBLIOTECA button with SAIR and library section title with JOGO INSTALADO.
4. Compute real fresh decoded Xbox frame FPS per monotonic second from guest decode serial,
   and show separate host Metal presentation Hz in top-left of the actual Vulkan surface.
   Static logo -> 0 real FPS, not 60 FPS.
5. Preserve actual filename errors; check the case-insensitive mapped filesystem paths
   for intro movie assets at boot and log XOWUE_ASSET_PREFLIGHT. Record whether XInput polls
   actually consumed changed touch packets (XOWUE_INPUT_POLLED).
6. Add CI regression tests requiring compiled/linked cancellation API and FPS tracking.

## Limits
- No in-device playthrough from this CI. Movie assets are owned by the user's game installation,
  not shipped in the IPA. Menu/gameplay is not proven until a test captures new guest swaps,
  new draws, input consumption, asset-load success, and title/menu state.
- No Xbox emulation/JIT/interpreter was added; native AOT and Xenos renderer retained.
- Only XOWUE branch may be updated; other branches untouched. 1 commit/1 workflow for delivery.
