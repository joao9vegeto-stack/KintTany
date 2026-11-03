# iOS guest-memory and ELF staging layer

The guest arena uses Apple's public `vm_allocate`, `vm_protect` and
`vm_deallocate` APIs. Guest addresses are offsets from the host base; no fixed
address reservation or private Mach VM headers are used.

`SpartanIOSGuestELFLoader` validates a reconstructed ELF64 little-endian
x86-64 header and program-header table, stages each `PT_LOAD` at its guest
virtual address, zero-fills BSS, records segment flags and requires the entry
point to lie in an executable segment. Guest pages remain data-only:
`PROT_EXEC` is rejected and ELF execute flags are metadata, not host page
permissions.

This accepts a reconstructed ELF only. It does not decrypt PS4 SELF, apply
dynamic relocations, load PRX dependencies, resolve imports, implement PS4
syscalls/threads/TLS, execute x86-64, or provide the GNM renderer. It is a
loader primitive, not a complete PS4 runtime. Game start remains blocked until
static ARM64 AOT, strict dispatch, HLE/imports, thread support and GNM/Metal
are implemented and linked.

Translation is offline. No JIT, runtime code generation, interpreter or
emulation fallback is permitted; an unimplemented reached instruction must
fail closed.


## G3PROBE5 linked-image staging

`SpartanIOSG3ProbeLoader` consumes the exact `G3PROBE5` container emitted by
`gow3-macos-arm64/scripts/link_modules.py`. It validates the module, binding,
segment, import-name and relocation tables; stages the linked image in data-only
guest memory; applies relative relocations, resolved module imports and GS/TLS
displacements; and returns the host-mapped entry address. Unresolved PS4 imports
are counted and left zero, never replaced by fake success values. The caller
must refuse game start while any remain. The image pages are never executable:
the separately compiled ARM64 AOT functions are the only executable game code.
