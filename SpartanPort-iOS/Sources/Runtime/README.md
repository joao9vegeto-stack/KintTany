# iOS guest-memory and JIT host layer

This directory is the first native Darwin host-services layer for the PS4 runtime port.

* Guest memory is a contiguous, relocatable arena. Guest virtual addresses are offsets
  from its base; this intentionally does not request Linux-style fixed low addresses.
* Per-range protection is implemented with Mach VM protections and checked bounds.
* Executable memory uses Apple's `MAP_JIT` contract and explicit per-thread W^X
  write-protection transitions. The app must be signed with the platform's permitted
  JIT entitlement/capability; allocation failure is propagated rather than bypassed.
* Instruction-cache invalidation is explicit after code generation.

This layer does **not** claim that FEXCore is already running on iOS. The upstream
FEX guest CPU currently depends on Linux signal-frame layouts, syscall handling,
`process_vm_readv`, and Linux VM behavior. Those interfaces must be ported to Darwin
and connected to this API before the x86-64 PS4 guest can execute. The PS4 GPU address
translation must also consume the arena base rather than assuming guest addresses
are host pointers.
