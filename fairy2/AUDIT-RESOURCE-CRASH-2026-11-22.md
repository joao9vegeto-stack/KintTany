# Fairy Tail 2 — global forensic investigation (22 November 2026)

Two separate iPhone 17 Pro crash logs: GPU encoder/prefetch OFF and ON; both end identically in CRASH sig=5 pc=main+0xbfe2a8. This is a deliberate resource-factory trap, not prior SIGSEGV in allocator list.
Real game ARM64 main: main+0xc108ec calls a virtual resource factory, main+0xc1098c branches on NULL, main+0xc10b84 references the string can't create resource Name[%s] Hash[0x%08x], main+0xc10b8c calls error handler and main+0xbfe2a8 triggers SIGTRAP.
The displayed crash memory was truncated after the first six words, but both crash contexts preserve x11=0x626539626678305b and x10=0x5d343264. In little-endian these reconstruct the exact suffix [0xfb9ebd24]. The complete resource diagnostic is: can't create resource Name[Unknown] Hash[0xfb9ebd24]. No evidence yet that this hash is missing on disk rather than a failed allocation/initialization; DM_FS=1 and DM_CRASH_PEEK=x1 will preserve future diagnostics.

Previous no-overlap build fixed 2GiB KTGL inner child: 0x36d800000..0x3ed800000, NVN 1290MiB ends 0x3d20ac000, next allocator bin47 is 0x3ed800178. Both logs verify relocation; original allocator corruption no longer occurs.
However original main v458752 requests 60GiB at five independent sites (0x5f1b9c, 0x1d700bc, 0x225de0c, 0x2295a44, 0x2295a50). Port reduced all to 4GiB; eight initial subregions reach 0x401200000, leaving 0x2ae00000 (~682 MiB) in original root to support later resources.
Pinned NXNative hle_svc.c documents a single 6GiB anonymous guest mmap succeeds on non-Extended-VA iOS, 7GiB fails. Therefore do not attempt 60GiB on the free-signed iPhone.
Coherent candidate: mem_reserve 0x180000000 (6GiB), mem_alias 0x158000000 (5.375GiB), same 128MiB heap and 256MiB stack, same alias base 0x328000000. Guest root becomes 0x140000000 (5GiB) and ends 0x46c000000; initial eight regions end 0x401200000, leaving 0x6ae00000 (~1.67GiB) for later resources.
Because 5GiB is not one MOVZ, use five independently verified branches to zero-padded guest code caves. Each cave builds 0x140000000 with MOVZ #1 shifted 32 and MOVK #0x4000 shifted 16 then returns. Preserve LR/flags/non-target regs and all 2GiB KTGL/heap/align sites. Source real work archive independently checked cave bytes are zero.
Keep original 19,210 Metal shaders, external RomFS (14,770 entries) and 16 DLCs, SVC device-shared guards, physical app-pool and memory budget, 30/60 options and A/B swap.
CI must assert source run 44995690307 IPA SHA b1792f9eb522de53b2b252e3a85229584831434999edda98f31c87c7c8c256cd; exact five-code-cave semantics; all hashes, proper 6GiB runtime profile, code signing and IPA CRC.
Do not call this a gameplay fix before a new iPhone test advances beyond the resource error. If unchanged, capture full hash and FS evidence for direct cause analysis.

Critical correction from failed build 45000042038 (not a game crash): real packaged main consists of THREE Mach-O segments, per pinned NXNative dm/host/loader.c:
- __TEXT,__dmmainx0: original RX 0..0x22d4000;
- __DMmainW,__img: guest RO/data W from 0x22d4000 to generated code PATCH_OFF 0x2c60000;
- __TEXT,__dmmainx1: generated executable RX from PATCH_OFF 0x2c60000 through the rounded end (observed main size 0x2d6c000).
The earlier repacker incorrectly treated __dmmainx0 alone as the entire guest. A purported cave at 0x2c5f000 would actually lie in W (non-executable), and is forbidden even if its bytes were zero. It was correctly rejected by validation, though the early error text misidentified the reason.
The repaired repacker explicitly concatenates three sections in GUEST offset order, checks x0 + W ends exactly at PATCH_OFF, validates only x0's prior guest SHA against the failed IPA report and checks x0/x1/W SHA separately.
The five 4GiB producer sites are in x0. The five new trampolines are placed ONLY in proven-zero bytes of executable x1 after PATCH_OFF. W remains bit-for-bit unchanged. The game-side branch is direct ARM64 B (within +/-128MiB), not a linker or code relocation guess.
These build failures did not produce usable IPAs. The new x0/W/x1-aware repacker has not yet been verified on the device.
