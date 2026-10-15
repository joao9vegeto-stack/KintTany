#!/usr/bin/env python3
"""Prepare a temporary ios CPU/SPU/LV2 runtime build from the PINNED upstream tree.
Do not change upstream remote or other project branches. Exclude desktop
SDL2 input/audio and AppKit Metal WINDOW backend until native adapters exist.
Fail loudly if any of the upstream CMake patterns change.
"""
import argparse
from pathlib import Path

def patch(content: str) -> str:
    replacements = [
        (
            'list(FILTER HLE_SOURCES EXCLUDE REGEX "/tests/")',
            '''list(FILTER HLE_SOURCES EXCLUDE REGEX "/tests/")
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    # Explicitly not built: desktop SDL2 implementations.
    # Guest HLE callers MUST NOT assume these work on iOS yet.
    list(FILTER HLE_SOURCES EXCLUDE REGEX "/cellPad\\\\.c$|/cellAudio\\\\.c$")
endif()'''
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
            '    message(STATUS "  Metal:       RSX backend enabled (rsx_metal_backend.m)")\nendif()',
            '''    message(STATUS "  Metal:       RSX backend enabled (rsx_metal_backend.m)")
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    target_link_libraries(ps3recomp_runtime PUBLIC
        "-framework Foundation"
        "-framework UIKit"
        "-framework Metal"
        "-framework QuartzCore")
    message(STATUS "  iOS: CPU/SPU/LV2 core only; native input/audio/RSX host adapters NOT included")
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

if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("cmake_file",type=Path)
    args=a.parse_args()
    src=args.cmake_file.read_text()
    args.cmake_file.write_text(patch(src))
    print("Applied iOS-only CPU/SPU/LV2 CMake overlay to disposable pinned checkout.")
