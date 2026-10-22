# Build21 - SIGBUS completely symbolized

**Source evidence**: real Build20 .ips on iPhone18,1 iOS 26.5.1, not a guessed shader issue. Faulting stack: __bzero+32 -> xbox_ContiguousAlloc+772 -> bridge_MmAllocateContiguousMemoryEx+212 -> kernel_thunk_dispatch -> recompiled retail x86 symbols. Faulting address host 0x3809B6000, Xbox VA 0x809B6000 with guest VM base 0x300000000. The iOS vmRegionInfo shows the page interval 0x3809B0000..0x3809B8000 has protection r--/rw- and adjacent parts of the SAME mapped file are rw-/rw-. Hence KERN_PROTECTION_FAILURE.

The upstream rePOP contiguous allocator already calls VirtualProtect(PAGE_READWRITE) before zeroing a reclaimed block, for texture pages previously set read-only/write-combined by PoP retail. But the upstream portable POSIX Win32 shim's VirtualProtect calls mprotect with the guest address unchanged, including 4KiB-aligned 0x809B6000 which is not 16KiB aligned. Darwin mprotect fails EINVAL. The allocator ignored the return, then __bzero wrote to the leftover r-- page.

**B21 fix**: On iOS only, round requested protection spans outwards to sysconf(_SC_PAGESIZE) host pages before calling mprotect. Check arithmetic overflows/invalid spans. Additionally in iOS contiguous allocator report failures and return 0 rather than bzero readonly memory. Preserve Linux/Android logic. Unit/source regression checks. No signal skipping, no fake textures/shaders, no guest recompiler changes. Increment all version fields to Build21/v2.1.

**Video**: 23s iPhone screen recording shows iOS launcher, LiveContainer install dialogue and the PoPTST launcher, not a verified rendered game scene. The blocking fault happens immediately after real retail entry and preceding first confirmed NV2A frame.

**Verification**: GitHub Actions iPhoneOS ARM64 Xcode compile + runtime source checks; real iPhone device must confirm moving beyond 0x809B6000. If a new fault occurs, address it from its symbolized .ips; don't claim render prior to evidence.
