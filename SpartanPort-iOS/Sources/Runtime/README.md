# iOS guest data-memory layer (AOT-only runtime)

This directory contains a data-memory primitive for the PS4 runtime port.

* Guest memory is a contiguous, relocatable **data** arena. Guest virtual
  addresses are offsets from its host base; Linux-style fixed low-address
  mappings are not requested.
* Per-range data-page protection is implemented with Mach VM protections and
  checked bounds.
* Executable pages are intentionally unsupported. The API rejects
  `PROT_EXEC`; there is no `MAP_JIT`, `pthread_jit_write_protect_np`,
  runtime code generator, or executable-memory allocator here.

## Required CPU execution model

The target is static ARM64 AOT recompilation. Translation must happen before
installation/build: x86-64 guest instructions are translated into ARM64
objects, those objects are linked into the signed iOS application, and the
runtime dispatches to already-linked native functions. No guest code is
translated or emitted while the game is running.

This memory arena is only a host data-memory primitive. It does **not** mean
that FEXCore or the PS4 CPU/GPU runtime is integrated. The upstream Android/Linux
port still needs its CPU execution path replaced by an offline AOT pipeline and
its Linux guest ABI/syscalls adapted to Darwin. GPU guest-address translation
must use the arena base rather than assuming guest addresses are host pointers.
