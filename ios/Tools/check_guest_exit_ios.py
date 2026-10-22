#!/usr/bin/env python3
"""Fail closed Build16 Xbox ExitProcess/signal checks."""
from pathlib import Path
import sys
repop=Path(sys.argv[1])
base=Path(__file__).resolve().parents[1]
c=(repop/'port/third_party/xboxrecomp/src/platform/win32_compat.c').read_text()
br=(repop/'port/third_party/xboxrecomp/src/kernel/kernel_bridge.c').read_text()
hal=(repop/'port/third_party/xboxrecomp/src/kernel/kernel_hal.c').read_text()
engine=(base/'Native/poptst_engine.c').read_text()
fault=(base/'Native/poptst_ios_fault.c').read_text()
boot=(base/'Runtime/poptst_retail_boot.c').read_text()
assert 'poptst_engine_guest_request_exit((unsigned)exitCode' in c
assert 'pthread_exit(NULL);' in c
assert 'ExitProcess(exitCode);' in c
assert 'XBOX HalReturnToFirmware routine=' in br
assert 'XBOX HAL firmware exit requested' in hal
assert 'void poptst_engine_guest_request_exit(unsigned code, uintptr_t caller)' in engine
assert 'atomic_store(&game_done,1);' in engine
assert 'sigaction(SIGFPE,&action,&old_fpe);' in fault
assert 'sigaction(SIGTRAP,&action,&old_trap);' in fault
assert 'AOT ENTER: xbe_entry_point 0x00335753' in boot
assert 'AOT RETURN: xbe_entry_point returned' in boot
print('PASS B16: exit handling and AOT/FPE/TRAP checkpoints')
