# PoPTST B19 SIGBUS — verified direct-sideload reproduction

## Evidence
Build 18 passed AOT and real D3D8 Xbox OUT8/WBINVD opcodes, then SIGBUS(10): host 0x3809b6000, PC 0x2acf82c20. User reproduced IDENTICAL fault addresses with direct iPhone sideload, not only LiveContainer. Missing TDATA/cache files may be separate filesystem symptoms, but cannot be declared direct cause of SIGBUS from existing data.

## B19 instrumentation and unchanged semantics
- Logs actual Xbox virtual-memory base, Mach-O executable image base and signal si_code in the signal handler. Decodes host fault to guest VA and ARM64 PC to dylib offset. Does not suppress or redirect faults.
- Logs host game/data roots and detailed native NtCreateFile error context: guest path, translated path, disposition, access, options, root handle.
- Maintains fail-closed unknown-opcode behavior. No fabricated game files, no change to GPU calls, AOT dispatch or memory mappings.
- Bumps UI and diagnostic build to 19 / v1.9. Tracks direct-sideload reproduction rather than attributing crash to LiveContainer.
- GitHub Actions retains 74 retail AOT sources, shader compilation, pinned rePOP, SDL3 and KosmicKrisp.
## Required iPhone evidence after B19
Collect Crash-Build-19.txt; inspect SIGDETAIL xbox_va (contiguous 0x80000000..0x83ffffff vs outside), si_code and dylib_offset; disassemble same B19 Mach-O before changing mapping semantics. If xbox_va points at contiguous file mapping, confirm physical backing and mmap offset/extent/ENOSPC. Missing contentmeta.xbx is not justification for placeholder saves. No gameplay claim without actual NV2A present.
## Constraints
One orphan root commit only on PoPTST; no modifications to PsTJohn, main, AscensionRecomp or rePOP upstream. Retail assets are not embedded.
