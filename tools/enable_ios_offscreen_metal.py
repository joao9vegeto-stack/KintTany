#!/usr/bin/env python3
"""Opt pinned upstream PS3Recomp RSX Metal into an OFFSCREEN iPhoneOS build.
Only modify disposable CI checkout, never the source repo or other branches.
"""
import argparse
from pathlib import Path

def edit_cmake(s: str) -> str:
    anchor='add_library(ps3recomp_runtime STATIC'
    if s.count(anchor)!=1:
        raise ValueError("Unexpected runtime library anchor")
    block='''if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    enable_language(OBJC)
    list(APPEND HLE_SOURCES "@SRC@/libs/video/rsx_metal_backend.m")
    set_source_files_properties(
        "@SRC@/libs/video/rsx_metal_backend.m"
        PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
endif()

'''.replace("@SRC@", "$"+"{CMAKE_CURRENT_SOURCE_DIR}")
    return s.replace(anchor,block+anchor,1)

def edit_metal(s: str) -> str:
    anchor='static NSWindow*           s_window;'
    if s.count(anchor)!=1:
        raise ValueError("Unexpected NSWindow state in upstream Metal backend")
    return s.replace(anchor, "#if !TARGET_OS_IPHONE\n"+anchor+"\n#endif",1)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmake_file",type=Path)
    args=ap.parse_args()
    root=args.cmake_file.parent
    cmake=args.cmake_file
    metal=root/"libs/video/rsx_metal_backend.m"
    edited_cmake=edit_cmake(cmake.read_text())
    edited_metal=edit_metal(metal.read_text())
    cmake.write_text(edited_cmake)
    metal.write_text(edited_metal)
    print("iOS OFFSCREEN Metal enabled, AppKit NSWindow excluded. No drawable or game rendering promised.")

if __name__=="__main__":
    main()
