# Build22 - B21 native AOT writable GPU physical page
Evidence: real iPhone18,1 LiveContainer .ips at 2026-10-22 01:55:36 (Bahia) and PoPTST-Crash-Build-21.txt.

## Verified
- Build20 crashed in Apple __bzero writing Xbox 0x809B6000. Build21 passes this previous point and crashes differently, now inside static retail AOT.
- Build21 signal SIGBUS KERN_PROTECTION_FAILURE at host 0x3808E8014 / guest 0x808E8014, within 16KiB mapped-file 0x3808E8000..0x3808EC000 r--/rw-, surrounded by rw-/rw-.
- Native PC dylib offset 0x12F41E0: ARM64 str w8, [x10, w9, uxtw], lifted function sub_003EA22A+856; not Vulkan/Metal.
- Pin rePOP 4ee36260e71d39fd8b02028fd614b1907a0d451b: xbox_MmSetAddressProtect sends PAGE_READONLY (including WRITECOMBINE flag) through VirtualProtect. Xbox virtual protections are 4KiB; iOS is 16KiB. Neighboring writable physical allocations may occupy one host page.

## B22 scope
- Only on iOS, for guest physical contiguous 0x80000000..0x84000000, treat PAGE_READONLY requests as a writable host GPU page to avoid denying independent guest 4KiB allocations. All other protection classes and regions are unchanged.
- Log first 24 GPU PAGE B22 policy decisions with VA, size, guest request, result/errno.
- Retain B21 rounded VirtualProtect and checked xbox_ContiguousAlloc permission restoration.
- This does not mean a rendered frame or correct texture semantics is verified. A full guest-protection ledger may be required for accurate 4KiB semantics.
- Version 22 / v2.2; strict PoPTST-only orphan commit and one GitHub Actions workflow.

## Remaining proof obligations
- Install B22 and check first actual frame / Vulkan SDL GPU present. If SIGBUS persists, symbolize next .ips and identify its actual instruction and protection setter.
- Verify texture uploads, NV2A pushbuffer execution, SDL GPU Vulkan pipeline via KosmicKrisp, and present only when guest reaches renderer.

## B22.1 compilation-only correction
Actions #30 exposed an ISO C99 diagnostic in kernel_memory.c: snprintf was undeclared. B22.1 adds <stdio.h> in the iOS-specific temporary upstream patch and adds a source regression check. No runtime policy changed. GitHub Actions #31 is the new build.
