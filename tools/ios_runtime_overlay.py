#!/usr/bin/env python3
"""Prepare a temporary ios CPU/SPU/LV2 runtime build from the PINNED upstream tree.
Do not change upstream remote or other project branches. Include the iOS
virtual-pad and silent-audio service adapters; keep desktop AppKit out of iOS.
Fail loudly if any of the upstream CMake patterns change.
"""
import argparse
from pathlib import Path

def patch(content: str) -> str:
    replacements = [
        (
            'list(FILTER HLE_SOURCES EXCLUDE REGEX "/tests/")',
            "list(FILTER HLE_SOURCES EXCLUDE REGEX \"/tests/\")\n"
            "# iOS uses this project's virtual-pad and silent-audio service adapters."
        ),
        (
            'if(APPLE)\n    enable_language(OBJC)',
            'if(APPLE AND NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")\n    enable_language(OBJC)'
        ),
        (
            'else()\n    # cellPad and cellAudio select their SDL2 backends unconditionally off',
            '''elseif(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    find_package(Threads REQUIRED)
    target_link_libraries(ps3recomp_runtime PRIVATE Threads::Threads)
else()
    # cellPad and cellAudio select their SDL2 backends unconditionally off'''
        ),
        (
            'if(APPLE)\n    target_link_libraries(ps3recomp_runtime PUBLIC',
            'if(APPLE AND NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")\n    target_link_libraries(ps3recomp_runtime PUBLIC'
        ),
        (
            '    message(STATUS "  Metal:        RSX backend enabled (rsx_metal_backend.m)")\nendif()',
            '''    message(STATUS "  Metal:        RSX backend enabled (rsx_metal_backend.m)")
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    target_link_libraries(ps3recomp_runtime PUBLIC
        "-framework Foundation"
        "-framework UIKit"
        "-framework Metal"
        "-framework QuartzCore")
    target_compile_definitions(ps3recomp_runtime PRIVATE
        PS3RECOMP_PAD_IOS=1 PS3RECOMP_AUDIO_IOS=1)
    message(STATUS "  iOS: cellPad virtual input, cellAudio service, RSX Metal host")
endif()'''
        ),
        (
            'if(UNIX)\n    find_package(glslang CONFIG QUIET)',
            'if(UNIX AND NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")\n    find_package(glslang CONFIG QUIET)'
        ),
    ]
    for before,after in replacements:
        count=content.count(before)
        if count!=1:
            raise ValueError(f'upstream CMake anchor count {count}, expected 1: {before[:75]!r}')
        content=content.replace(before,after,1)
    return content

def patch_mach_vm(content: str) -> str:
    """Use public iOS vm_region_64 when macOS-only mach_vm.h is unavailable.

    The region query is NOT stubbed out: preserving real VM address
    protection and mapping information is necessary for correctness.
    """
    replacements = [
        (
            '#  include <mach/mach_vm.h>',
            '#  include <TargetConditionals.h>\n'
            '#  if !TARGET_OS_IPHONE\n'
            '#    include <mach/mach_vm.h>\n'
            '#  endif'
        ),
        (
            '    mach_vm_address_t a = (mach_vm_address_t)addr;\n'
            '    mach_vm_size_t    sz = 0;',
            '#if TARGET_OS_IPHONE\n'
            '    vm_address_t a = (vm_address_t)addr;\n'
            '    vm_size_t    sz = 0;\n'
            '#else\n'
            '    mach_vm_address_t a = (mach_vm_address_t)addr;\n'
            '    mach_vm_size_t    sz = 0;\n'
            '#endif'
        ),
        (
            '    kern_return_t kr = mach_vm_region(mach_task_self(), &a, &sz, VM_REGION_BASIC_INFO_64,\n'
            '                                      (vm_region_info_t)&info, &cnt, &name);',
            '#if TARGET_OS_IPHONE\n'
            '    kern_return_t kr = vm_region_64(mach_task_self(), &a, &sz, VM_REGION_BASIC_INFO_64,\n'
            '                                    (vm_region_info_t)&info, &cnt, &name);\n'
            '#else\n'
            '    kern_return_t kr = mach_vm_region(mach_task_self(), &a, &sz, VM_REGION_BASIC_INFO_64,\n'
            '                                      (vm_region_info_t)&info, &cnt, &name);\n'
            '#endif'
        )
    ]
    for before, after in replacements:
        count=content.count(before)
        if count!=1:
            raise ValueError(f'Apple Mach region overlay anchor count {count}, expected 1: {before[:80]!r}')
        content=content.replace(before,after,1)
    return content

if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("cmake_file",type=Path)
    args=a.parse_args()
    src=args.cmake_file.read_text()
    args.cmake_file.write_text(patch(src))
    source = args.cmake_file.parent / "runtime/platform/win32_compat.c"
    source.write_text(patch_mach_vm(source.read_text()))
    print("Applied iOS CPU/SPU/LV2 CMake and vm_region_64 overlays in disposable pinned checkout.")
