# XOWUE Build 34: cause-specific native boot repairs

## iPhone Build 33 evidence (24 Oct 2026)
- Native memory regression from Build 32 fixed: first NtAllocateVirtualMemory allocated at 0x40000000, returned status 0.
- 148,761 AOT calls, 6,973 distinct guest functions and 26 captured Xenos draws (25 sent to Vulkan), but zero color readback pixels.
- PPC abort exactly at 0x82361BF4 (bctrl, CTR 0), LR 0x82361BF8, r3=0 following preceding indirect call at 0x82361BE0. Do **not** synthesize a valid CTR or skip this branch.
- 144 occurrences of "NtFree MEM_RELEASE rejected interior" in cumulative diagnostic data; contiguous guest allocations 0x40120000, 0x40130000 revealed half-open boundary selection bug.
- Several NtCreateFile failures logging attrs first word 0xFFFFFFFD, second word guest pointer, third 0x40. These match Xbox X_OBJECT_ATTRIBUTES layout, **not** Win32 OBJECT_ATTRIBUTES. See Xenia xenia/src/xenia/xbox.h X_OBJECT_ATTRIBUTES (root_directory/name_ptr/attributes at 0/4/8) and xboxkrnl_io.cc handling of ObDosDevices root 0xFFFFFFFD.
- 26 Xenos guest draws but no usable color surface for tile 720, so unable to claim rendered game frame.
- In the iPhone video user tapped "Voltar à biblioteca" repeatedly but the UIKit-hosted game remained presented.

## Corrective code
1. Runtime/XOWUEEngine.cpp: Xbox X_OBJECT_ATTRIBUTES root at 0, name pointer at 4, attributes at 8; restore valid game path parsing for NtCreateFile/NtOpenFile.
2. Runtime/XOWUEEngine.cpp: NtFreeVirtualMemory MEM_RELEASE selects exact starting address rather than treating previous reservation's exclusive end as inside it. Decommit still selects genuine containment.
3. iOS/App/XOWUEApp.swift: on Back explicitly release controls, set library state false, dismiss XOWUELandscapeHostingController, restore portrait and log outcome.
4. Python CI regression checks verify the offsets, exact interval behavior, and UIKit dismissal.

## Safety and conditions
- Only XOWUE branch. No interpreter/JIT/emulator. No fabricated guest targets, pixel content, or boot success.
- GitHub CI verifies integration and packaging but cannot prove Wolverine renders on device.
- Expected log change: valid NtCreateFile paths, MEM_RELEASE no longer rejected due to next-region endpoint selection, and possible continuation beyond old AOT crash; new on-device diagnostics will decide.
- If AOT still fails at 0x82361BF4, inspect the preceding call result and full object/file load semantics. No arbitrary address substitution.
