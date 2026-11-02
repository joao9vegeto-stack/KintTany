# iOS guest data-memory layer (AOT-only runtime)

The guest arena is allocated with Apple's public `vm_allocate`, `vm_protect`
and `vm_deallocate` APIs. The iOS SDK intentionally rejects
`<mach/mach_vm.h>`; using the unsupported 64-bit Mach VM header caused the
first Xcode 26 simulator test build to fail. On arm64, the public
`vm_address_t` and `vm_size_t` are pointer-width and support the 64-bit arena.

* Guest addresses are offsets from the host base; no Linux low-address mapping
  or fixed-address reservation is assumed.
* Page protection accepts only read/write. `PROT_EXEC` is rejected.
* Tests cover bounds, zero-length end pointers and executable-protection denial.

This is only a host data-memory primitive. It is not a PS4 CPU, GPU or syscall
runtime and does not translate x86-64 instructions.

## Required CPU execution model

The target remains static ARM64 AOT recompilation: translation must happen
offline, before installation/build, and generated ARM64 objects must be linked
into the signed application. Runtime code generation, JIT and executable guest
memory are intentionally absent.
