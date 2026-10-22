#!/usr/bin/env python3
"""Check pinned rePOP post-apply for safe iPhoneOS VM and failure telemetry."""
import sys
from pathlib import Path
root=Path(sys.argv[1]); compat=(root/'port/third_party/xboxrecomp/src/platform/win32_compat.c').read_text()
mem=(root/'port/third_party/xboxrecomp/src/kernel/xbox_memory_layout.c').read_text()
km=(root/'port/third_party/xboxrecomp/src/kernel/kernel_memory.c').read_text()
boot=Path(__file__).resolve().parents[1].joinpath('Runtime/poptst_retail_boot.c').read_text()
engine=Path(__file__).resolve().parents[1].joinpath('Native/poptst_engine.c').read_text()
hud=Path(__file__).resolve().parents[1].joinpath('Native/poptst_touch_overlay.m').read_text()
checks={
 '4GiB PROT_NONE': 'defined(__APPLE__) && TARGET_OS_IPHONE' in compat and 'p = mmap(address, size, PROT_NONE, flags, -1, 0);' in compat,
 'private RAM file': 'PoPTST-RAM-XXXXXX' in compat and 'mkstemp(temp_path)' in compat and 'unlink(temp_path)' in compat,
 'owned range only': 'owned_range(baseAddr, len)' in compat and 'if (baseAddr && owned_range' in compat,
 'reserved 4GiB': 'g_span_size = (size_t)0x100000000ull;' in mem,
 'VM stage': 'poptst_vm_set_failure' in mem and 'poptst_ios_vm_failure_detail' in mem and 'CreateFileMapping(RAM)' in mem,
 'fail closed aperture': 'aperture contig=' in mem,
 'VM status visible': 'poptst_ios_vm_failure_detail' in boot,
 'persistent device trace': 'poptst_engine_trace' in mem and 'VM: base file mapping succeeded' in mem and 'VM: RAM mirrors and extended VMA initialized' in mem,
 'overlay only on actual AOT': engine.index('poptst_engine_guest_entered_aot();') if 'poptst_engine_guest_entered_aot();' in engine else 'poptst_engine_guest_entered_aot' in boot,
 'HUD cleanup': 'poptst_ios_touch_overlay_uninstall' in engine and 'removeFromSuperview' in hud,
 'Exit button': '@"EXIT"' in hud and 'poptst_engine_exit_to_launcher' in hud,
 'native trace recorder': 'poptst_engine_signal_event' in engine and 'poptst_engine_set_trace_path' in engine,
 'host page aligned VirtualProtect': 'long n = sysconf(_SC_PAGESIZE);' in compat and 'uintptr_t lo = start & ~(page - 1u);' in compat and 'uintptr_t hi = (end + page - 1u) & ~(page - 1u);' in compat and 'mprotect((void *)lo, (size_t)(hi - lo)' in compat,
 'fail-closed reclaimed contiguous allocation': 'FATAL CONTIG PROTECT' in mem and 'return 0; /* Do not clear a read-only or unowned host page. */' in mem,
 'B22 stdio for GPU trace': '#include <stdio.h>' in km,
 'B22 narrow GPU RO policy': '(NewProtect & 0xffu) == PAGE_READONLY' in km and 'guest >= 0x80000000ull && guest < 0x84000000ull' in km and '0x84000000ull - guest' in km and 'PAGE_READWRITE, &old_protect' in km and 'GPU PAGE B22:' in km,
 'B22 other memory permissions preserved': 'VirtualProtect(BaseAddress, NumberOfBytes, xbox_protect_to_win32(NewProtect), &old_protect);' in km,
}
# Avoid a false test that checks a symbol but not its call in the guest boot.
checks['overlay only on actual AOT']='poptst_engine_guest_entered_aot();' in boot and 'SDL_ShowWindow(window);' in engine
for k,ok in checks.items():
    print(('PASS' if ok else 'FAIL'),k)
if not all(checks.values()):raise SystemExit(1)
