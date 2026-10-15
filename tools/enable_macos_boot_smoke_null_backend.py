#!/usr/bin/env python3
"""Make ONLY the macOS CI synthetic PPU/LV2 boot smoke use headless RSX.

The real iPhone Metal backend and guest shader compiler remain unchanged.
The pinned upstream smoke defaults to Metal on Apple even on headless CI,
leaving guest FIFO unconsumed and vblank uncalled. The upstream software
null backend is the correct deterministic oracle for the non-graphics boot
test. It still checks the actual FIFO, 3 flips, vblank, thread, HLE and exit.
"""
import argparse
from pathlib import Path

def patch(cmake: str, boot: str):
    target='        target_link_libraries(ps3recomp_boot_smoke PRIVATE ps3recomp_runtime)'
    if cmake.count(target)!=1:
        raise ValueError("pinned boot target anchor missing")
    cmake=cmake.replace(target,target+'''
        # M5.0.1 synthetic HOST-only CI: run software FIFO without window server.
        target_compile_definitions(ps3recomp_boot_smoke PRIVATE
            ASCENSIONRECOMP_BOOT_SMOKE_NULL_RSX=1)''',1)
    old='#elif defined(__APPLE__)\nextern "C" int  rsx_metal_backend_init'
    if boot.count(old)!=1:
        raise ValueError("pinned boot renderer selection drift")
    boot=boot.replace(old,'#elif defined(__APPLE__) && !defined(ASCENSIONRECOMP_BOOT_SMOKE_NULL_RSX)\nextern "C" int  rsx_metal_backend_init',1)
    return cmake,boot

def apply(upstream:Path):
    c=upstream/'CMakeLists.txt'
    b=upstream/'runtime/ppu/tests/boot_main.cpp'
    a,d=patch(c.read_text(),b.read_text())
    c.write_text(a)
    b.write_text(d)
    print('M5.0.1 host boot smoke uses deterministic headless software RSX only.')

if __name__=='__main__':
    cli=argparse.ArgumentParser()
    cli.add_argument('upstream',type=Path)
    apply(cli.parse_args().upstream)
