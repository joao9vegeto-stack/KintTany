# Build 20 - iPhone B19 log / reference port Android audit

Reference: FulGerNet/rePOP branch reSOT pinned 4ee36260e71d39fd8b02028fd614b1907a0d451b, port/android/src/main_android.c, SaveFolders.java, port/android/CMakeLists.txt and runtime kernel_path.c.

## Confirmed B19 device evidence
Xbox guest base 0x300000000; fatal host address 0x3809B6000, confirmed Xbox VA 0x809B6000. Signal 10 SIGBUS, si_code 1. The guest address falls 0x9B6000 bytes inside the 64MiB contiguous/physical memory aperture 0x80000000..0x84000000. Do NOT treat this as LiveContainer-only: user direct sideload reproduced identical fault. ARM64 fault PC 0x2ACF82C20 is outside the retail dylib image. Exact system call/instruction remains unknown until link register and native symbolication.

## Upstream parity
1. Same 74 generated retail x86 lifted C files; same SDL3, Vulkan native shader path, same 64MiB guest thread stack, same 4GiB guest reservation and disk partition emulation.
2. Android's SaveFolders.prepare copies missing TDATA/UDATA and legacy saves into writable /saves/xbox-retail while preserving newer files; B19 iOS lacked this migration. Build20 ports it.
3. PoPTST B19 translated Xbox E:/Partition1/CACHE/LocalCache00.bin (NtCreateFile disposition=3) into the *installed read-only game tree* /xbox-retail/CACHE where parent directory does not exist. The generic rePOP Partition1 mapping is valid for asset-drive titles but wrong for this writable retail cache path. Build20 inserts a specific Partition1/CACHE -> /saves/xbox-retail/Cache rule ahead of the generic rule and leaves bare raw partition images untouched.
4. Android crash logger includes PC and LR; B19 iOS only PC. B20 captures AArch64 LR, SP, x0-x3 in the existing async-signal-safe crash file to identify the native access that dereferences 0x809B6000.
5. B19 Info.plist was already v1.9/build19, but project Marketing Version/Current Version and display name remained 1.8/build18 ("PoPTST B18" in user video). B20 synchronizes all to 2.0/20.

## Outcome criteria
- Verify Actions success; install on device.
- Crash file may confirm cache open no longer ENOENT; this is a concrete behavior correction, not a proven SIGBUS fix.
- If same SIGBUS, LR/x0-x3 pin native call and show whether mapped contiguous pages were unmapped, protected, or backing object encountered SIGBUS. Do not invent rendering/gameplay claims.
- Branch PoPTST root orphan only, one commit / one workflow; no upstream changes or embedded game assets.
