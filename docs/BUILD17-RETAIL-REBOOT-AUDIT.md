# PoPTST BUILD 17 — Retail quick-reboot analysis

## Verified facts from uploaded B16 logs
Two separate attempts reached AOT entry at 0x00335753; each requested
Xbox HalReturnToFirmware routine=2 after about 2-3 milliseconds, then
ExitProcess code 0. This was an Xbox-guest requested quick-reboot (not
a recorded SIGSEGV). Guest ESP 0x00F7EFB8. Repeating "Local folder"
after termination failed because the already-created SDL window is
intentionally not destroyed while Xbox device worker threads may run.

## Root-cause candidate discovered by source parity audit
Pinned rePOP retail's Android POSIX path has:
- synthetic Partition0..5 raw disk image creation in sandbox;
- Partition0 partition table and Partition5 backing (sparse files);
- mapping bare partition requests to those images;
- native directory handling for Partition1 free-space probe;
- UDATA/TDATA mapping of U: / T: paths;
- case-insensitive path lookup; directory contexts and save offsets.

These paths were gated by __ANDROID__ and absent from iOS. Retail's
Android code explicitly cites guest address 0x00337414 for the
Partition1 free-space probe. A title can quick-reboot on a storage
check failure. **That is a reasoned hypothesis, not yet proven by B16
logs**; without the guest call stack or launch data page we cannot
declare it the only cause.

## Build17 changes
- iOS shares the POSIX retail Android disk/path/file semantics only
  under TARGET_OS_IPHONE; no fake successful syscalls and no assets
  inserted into the app.
- Partition backing results and early NtCreateFile failure paths now
  persist in PoPTST-Crash-Build-17.txt.
- Firmware quick-reboot snapshots launch data page and six stack
  DWORDs, to isolate caller/reason, preserving x86 register state.
- Blocks misleading second native boot in one process after guest AOT
  exited and VM/GPU threads remain mapped, advising app restart.
- UI/diagnostic version 17 / 1.7.
- No changes to PsTJohn, main or AscensionRecomp, orphan root only.

## How to interpret next device result
If AOT advances further without a quick reboot, confirm first
NV2A frame and actual game menu; compilation alone proves neither.
If HalReturnToFirmware(2) still fires:
- Inspect XBOX BOOT EXIT stack guest return addresses, launch page and
  file failure lines. Compare with retail rePOP generated C and x86 VAs.
- If a nonzero launch page has path pointing to another XBE, this may
  be a legitimate title/image swap rather than disk failure.
- If partition creation FAILED inspect storage quota / POSIX errno,
  not memory-limit entitlement.
- If no partition/file failure and immediate reboot, instrument exact
  guest code address and kernel call reasons; do not suppress reboot
  or forge STATUS_SUCCESS.

Sources pinned:
- FulGerNet/rePOP branch reSOT SHA 4ee36260e71d39fd8b02028fd614b1907a0d451b
- PsTJohn KosmicKrisp SHA db014165eb39429ae37d1946db6fc83c600c63b3
- User B16 crash and diagnostic, 2026-10-22 UTC
- Repo joao9vegeto-stack/KintTany branch PoPTST
