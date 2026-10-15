#!/usr/bin/env python3
"""M5.0: enable real guest VP/FP translation in a disposable pinned iPhoneOS build.

The two source dependencies are independently pinned by the workflow. Nothing
commercial is shipped in CI. Refuse to patch if upstream API anchors drift.
"""
import argparse
from pathlib import Path

GUEST_CMAKE = r'''
# AscensionRecomp M5.0 -- native, on-device RSX guest translator.
# Build Khronos C++ sources for iphoneos arm64, NOT macOS Homebrew dylibs.
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
    set(BUILD_EXTERNAL OFF CACHE BOOL "" FORCE)
    set(GLSLANG_TESTS OFF CACHE BOOL "" FORCE)
    set(GLSLANG_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
    set(ENABLE_GLSLANG_BINARIES OFF CACHE BOOL "" FORCE)
    set(ENABLE_SPVREMAPPER OFF CACHE BOOL "" FORCE)
    set(ENABLE_OPT OFF CACHE BOOL "" FORCE)
    set(ENABLE_PCH OFF CACHE BOOL "" FORCE)
    set(ENABLE_HLSL ON CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_STATIC ON CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_SHARED OFF CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_CLI OFF CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_ENABLE_TESTS OFF CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_ENABLE_MSL ON CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_ENABLE_GLSL ON CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_ENABLE_HLSL OFF CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_ENABLE_CPP OFF CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_ENABLE_REFLECT OFF CACHE BOOL "" FORCE)
    set(SPIRV_CROSS_ENABLE_UTIL OFF CACHE BOOL "" FORCE)
    set(AR_SHADER_DEPS "${CMAKE_CURRENT_SOURCE_DIR}/../ios-shader-deps")
    if(NOT EXISTS "${AR_SHADER_DEPS}/glslang/CMakeLists.txt"
       OR NOT EXISTS "${AR_SHADER_DEPS}/SPIRV-Cross/CMakeLists.txt")
        message(FATAL_ERROR "M5.0 requires pinned iPhoneOS Khronos shader dependencies")
    endif()
    add_subdirectory("${AR_SHADER_DEPS}/glslang" "${CMAKE_CURRENT_BINARY_DIR}/ar-glslang")
    add_subdirectory("${AR_SHADER_DEPS}/SPIRV-Cross" "${CMAKE_CURRENT_BINARY_DIR}/ar-spirv-cross")
    if(NOT TARGET glslang::glslang OR NOT TARGET glslang::SPIRV
       OR NOT TARGET spirv-cross-c)
        message(FATAL_ERROR "M5.0 guest shader compiler libraries unavailable")
    endif()
    target_compile_definitions(ps3recomp_runtime PRIVATE PS3RECOMP_HAVE_MSL_TRANSLATION=1)
    target_include_directories(ps3recomp_runtime PRIVATE "${AR_SHADER_DEPS}/SPIRV-Cross")
    target_link_libraries(ps3recomp_runtime PRIVATE
        glslang::glslang glslang::SPIRV spirv-cross-c)
    if(TARGET glslang::glslang-default-resource-limits)
        target_link_libraries(ps3recomp_runtime PRIVATE
            glslang::glslang-default-resource-limits)
    endif()
    message(STATUS "M5.0: iPhoneOS native glslang -> SPIR-V -> SPIRV-Cross MSL ENABLED")
endif()
'''

def patch(cmake: str, translator: str):
    cmake_anchor = '# Guest shaders on Vulkan: HLSL -> SPIR-V. glslang only -- Vulkan consumes'
    if cmake.count(cmake_anchor) != 1:
        raise ValueError("pinned upstream shader CMake section changed")
    if cmake.count('if(UNIX AND NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")') != 1:
        raise ValueError("apply ios_runtime_overlay.py first (no host dylib on iOS)")
    cmake = cmake.replace(cmake_anchor, GUEST_CMAKE + '\n' + cmake_anchor, 1)
    old = 'spvc_compiler_options_set_uint(opt, SPVC_COMPILER_OPTION_MSL_PLATFORM, SPVC_MSL_PLATFORM_MACOS);'
    if translator.count(old) != 1:
        raise ValueError("pinned SPIRV-Cross platform selector changed")
    translator = translator.replace(old, '''#if defined(__ENVIRONMENT_IPHONE_OS_VERSION_MIN_REQUIRED__)
    spvc_compiler_options_set_uint(opt, SPVC_COMPILER_OPTION_MSL_PLATFORM, SPVC_MSL_PLATFORM_IOS);
#else
    spvc_compiler_options_set_uint(opt, SPVC_COMPILER_OPTION_MSL_PLATFORM, SPVC_MSL_PLATFORM_MACOS);
#endif''', 1)
    return cmake, translator

def apply(upstream: Path):
    c = upstream / 'CMakeLists.txt'
    t = upstream / 'libs/video/rsx_shader_msl.cpp'
    new_c, new_t = patch(c.read_text(), t.read_text())
    c.write_text(new_c)
    t.write_text(new_t)
    print("M5.0: guest RSX VP/FP compiler enabled on iPhoneOS (MSL iOS platform).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    apply(parser.parse_args().upstream)
