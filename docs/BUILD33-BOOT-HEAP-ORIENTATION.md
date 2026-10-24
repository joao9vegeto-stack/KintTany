# XOWUE Build 33 — boot regression and presentation

## Build 32 iPhone observation (2026-10-24, title 41560816)
* XEX loaded base 0x82000000, entry 0x82C3CAA8, resolved imports 261.
* First observed NtAllocateVirtualMemory: requested=0, size=0x00100000, flags=0x60002000, protect=4, returned NTSTATUS 0xC0000017.
* Guest invokes HalReturnToFirmware(1) at LR=0x82C44F28, PPC callsite=0x82C44F24.
* AOT only 5 calls / 5 guest functions. Xenos never initialized, 0 draws / 0 swaps / 0 decoded frames. Host presents aren't game frames.
* Landscape request failed with "Supported: portrait", despite project Info.plist accepting landscape; screenshot taken before scene rotated.
* Crash file empty because no fatal iOS exception or signal occurred. Firmware return is controlled and correctly recorded in diagnostic-build file.

## Root cause in the Build 32 native C++ source
Function allocateGuestPhysicalRange was partially refactored into a physical heap:
* candidate originates at 0x10000000 and physical allocations stored in g_physicalAllocations
* BUT it mistakenly wrote candidate+size to g_nextVirtualAllocation (virtual heap cursor), not g_nextPhysicalAllocation
* it also tested candidate+size against kLastVirtualAllocation instead of physical upper bound
* First physical allocation corrupted virtual cursor to roughly 0x10001000; virtual auto reserve checks candidate>=kFirstVirtualAllocation=0x40000000 and returns STATUS_NO_MEMORY for a valid 1MiB request.

## Build 33 corrections
* Physical allocations now update g_nextPhysicalAllocation only and enforce kLastPhysicalAllocation.
* Regression assertion scopes to the definition body and forbids any physical function writes to g_nextVirtualAllocation or reference to virtual upper bound.
* Expanded NtAllocateVirtualMemory trace reports both cursors and returned status to verify actual on-device effect.
* UIKit UIHostingController presented as a native full-screen controller advertises .landscapeRight, instead of relying on SwiftUI's portrait-only fullScreenCover hosting controller. The library stays portrait.
* Empty crash files are hidden from Share; controlled firmware-return remains in diagnostico-build-N.txt.

## Must verify on actual iPhone
* First NtAllocateVirtualMemory returns success with requested size=0x100000 and expected guest virtual address 0x40000000, while physical cursor remains in 0x10000000 range.
* AOT proceeds beyond 5 functions; next blocker must be inspected, not bypassed or replaced with interpreter/JIT.
* Landscape orientation holds when game surface is presented, without portrait-only view-controller rejection.
* Actual Xenos shaders/draws and nonblack frames are not yet proven by this build.
* Exact code validation: one branch XOWUE commit; other branches untouched.
