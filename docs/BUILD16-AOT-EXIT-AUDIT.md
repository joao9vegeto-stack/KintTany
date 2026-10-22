# PoPTST Build 16 — AOT exit audit

Build 15 files: after 4GiB mapping/alias, APU/kernel, OHCI/dispatch,
the last recorded step is "Executando código Xbox retail x86 recompilado
para ARM64...". There was no SIGSEGV, SIGBUS, SIGILL or SIGABRT recorded.
This does not prove an instruction in the guest executed successfully.

Source audit: pinned rePOP win32_compat.c ExitProcess calls exit() on Apple
(including iOS), TerminateProcess calls exit(). Xbox kernel
HalReturnToFirmware can reach ExitProcess. A clean guest-requested exit
could therefore kill LiveContainer without any fault signal.
This is a proven portability defect and a plausible, UNCONFIRMED cause
of Build 15 exit.

Build 16 remedies:
- iOS-only ExitProcess and TerminateProcess record status and stop the
  requesting guest thread, keeping the SwiftUI/LiveContainer host alive.
- HAL firmware/bridge routine and guest ESP logged before process-exit.
- SIGFPE and SIGTRAP added to fault recorder (still re-raised).
- AOT entry and return checkpoints, libc atexit breadcrumb.
- Version 16 shown on UI and saved logs; no changes to other branches.

If Build 16 still closes after AOT ENTER with no signal: examine LiveContainer
host process .ips, jetsam reports, platform SIGKILL or other unchecked exits.
If Xbox ExitProcess logged: investigate firmware routine/ESP/launch data.
If FATAL SIGNAL: symbolize ARM64 PC; never replace game logic with fake data.
B16 still does not demonstrate first frame or gameplay.

Upstream rePOP 4ee36260e71d39fd8b02028fd614b1907a0d451b;
PsTJohn KosmicKrisp db014165eb39429ae37d1946db6fc83c600c63b3.
Branch joao9vegeto-stack/KintTany PoPTST (orphan root only).
