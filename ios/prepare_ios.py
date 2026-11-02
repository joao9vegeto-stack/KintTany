#!/usr/bin/env python3
"""Prepare upstream Asura/ReXGlue sources for an arm64 iOS app build.

The ReXGlue SDK currently labels all Apple targets as mac-arm64. iOS is also
AppleClang/ARM64 and its SDL Metal surface is the CAMetalLayer path, so retain
that ABI/platform code while marking the actual target as iOS for guarded code.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cmake = root / "CMakeLists.txt"
text = cmake.read_text()
needle = 'set_target_properties(asura_wrath_recomp PROPERTIES OUTPUT_NAME "asura_wrath_recomp")'
assert text.count(needle) == 1, "unexpected upstream CMake target layout"
replacement = needle + '''
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
  target_sources(asura_wrath_recomp PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/ios/kosmickrisp_probe.m")
  target_sources(asura_wrath_recomp PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/ios/asura_ios_native.mm")
  set_source_files_properties(ios/asura_ios_native.mm PROPERTIES COMPILE_FLAGS "-fobjc-arc -fblocks")
  target_compile_definitions(asura_wrath_recomp PRIVATE ASURA_IOS_BUILD_NUMBER=\"${ASURA_IOS_BUILD_NUMBER}\")
  target_link_libraries(asura_wrath_recomp PRIVATE
    "-framework UIKit" "-framework Metal" "-framework QuartzCore"
    "-framework Foundation" "-framework GameController"
    "-framework UniformTypeIdentifiers")
  set_target_properties(asura_wrath_recomp PROPERTIES
    MACOSX_BUNDLE TRUE
    MACOSX_BUNDLE_GUI_IDENTIFIER "com.joaopedro.asuraswrath"
    MACOSX_BUNDLE_BUNDLE_NAME "Asura's Wrath"
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/ios/Info.plist")
endif()
'''
cmake.write_text(text.replace(needle, replacement))

sdk = root / "tools/rexglue/CMakeLists.txt"
sdk_text = sdk.read_text()
needle = '    add_compile_definitions(REX_PLATFORM_MAC=1)'
assert sdk_text.count(needle) == 1, "ReXGlue Apple platform block changed"
sdk.write_text(sdk_text.replace(needle, needle + '''
    if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
        add_compile_definitions(REX_PLATFORM_IOS=1)
    endif()
'''))
# MoltenVK's CMake project requires AppKit, which is not part of the
# iPhoneOS SDK. iOS uses the bundled KosmicKrisp ICD, so retain the Vulkan
# loader but do not configure the macOS MoltenVK implementation.
thirdparty_cmake = root / "tools/rexglue/thirdparty/CMakeLists.txt"
thirdparty_text = thirdparty_cmake.read_text()
moltenvk_needle = "        add_subdirectory(moltenvk)"
assert thirdparty_text.count(moltenvk_needle) == 1, "unexpected MoltenVK dependency block"
thirdparty_cmake.write_text(thirdparty_text.replace(
    moltenvk_needle,
    """        if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
            add_subdirectory(moltenvk)
        endif()"""
))


# ReXGlue's generic Apple target setup also stages the macOS Vulkan runtime.
# Skip that POST_BUILD hook for iOS: its Vulkan implementation is the separately
# bundled KosmicKrisp ICD, not MoltenVK.
helpers_cmake = root / "tools/rexglue/cmake/rexglue_helpers.cmake"
helpers_text = helpers_cmake.read_text()
stage_needle = "    if(APPLE AND REXGLUE_USE_VULKAN)"
assert helpers_text.count(stage_needle) == 1, "unexpected ReXGlue Vulkan staging condition"
helpers_cmake.write_text(helpers_text.replace(
    stage_needle,
    '    if(APPLE AND NOT CMAKE_SYSTEM_NAME STREQUAL "iOS" AND REXGLUE_USE_VULKAN)'
))

ui = root / "tools/rexglue/src/ui/CMakeLists.txt"
ui_text = ui.read_text()
assert 'elseif(APPLE)\n    set(REXUI_PLATFORM_SOURCES' in ui_text
# iOS SDL_Metal_CreateView returns a CAMetalLayer-backed UIView; use the same
# SDL Metal surface implementation while compiling against the iPhoneOS SDK.
ui.write_text(ui_text.replace('elseif(APPLE)\n    set(REXUI_PLATFORM_SOURCES',
                              'elseif(APPLE)\n    set(REXUI_PLATFORM_SOURCES', 1))

# The bundled Vulkan-Loader derives SYSTEM_PROCESSOR from
# CMAKE_SYSTEM_PROCESSOR. CMake's iOS/Xcode toolchain can leave that empty
# even with CMAKE_OSX_ARCHITECTURES=arm64, which makes its unquoted
# "if(WIN32 AND ${SYSTEM_PROCESSOR} MATCHES ...)" expressions syntactically
# invalid. Seed the loader's own architecture variable from the selected
# Apple target architecture before it configures its loader subdirectory.
loader_cmake = root / "tools/rexglue/thirdparty/vulkan-loader/CMakeLists.txt"
loader_text = loader_cmake.read_text()
loader_needle = '    string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" SYSTEM_PROCESSOR)'
assert loader_text.count(loader_needle) == 1, "unexpected Vulkan-Loader architecture detection"
loader_replacement = loader_needle + '''
    if(NOT SYSTEM_PROCESSOR AND CMAKE_OSX_ARCHITECTURES)
        string(TOLOWER "${CMAKE_OSX_ARCHITECTURES}" SYSTEM_PROCESSOR)
    endif()
    if(NOT SYSTEM_PROCESSOR)
        message(FATAL_ERROR "Vulkan-Loader could not determine target architecture")
    endif()
'''
loader_cmake.write_text(loader_text.replace(loader_needle, loader_replacement))


# ReXGlue's SDL window source is missing the closing brace for the
# CAMetalLayer allowed-types branch. Close it before the Android branch.
window_sdl = root / "tools/rexglue/src/ui/window_sdl.cpp"
window_sdl_text = window_sdl.read_text()
surface_needle = """      SDL_Metal_DestroyView(metal_view);
    }
#elif REX_PLATFORM_ANDROID
"""
surface_replacement = """      SDL_Metal_DestroyView(metal_view);
    }
  }
#elif REX_PLATFORM_ANDROID
"""
assert window_sdl_text.count(surface_needle) == 1, "unexpected ReXGlue SDL Metal surface block"
window_sdl.write_text(window_sdl_text.replace(surface_needle, surface_replacement))

# ReXGlue currently treats every Apple target as macOS in its POSIX memory
# backend. iOS ships mach/mach.h but explicitly rejects mach/mach_vm.h, and
# mach_vm_region is unavailable in the iPhoneOS SDK. Keep the macOS region
# query on macOS only; iOS uses the existing conservative non-Linux fallback
# in QueryProtect (the API reports that the prior protection is unavailable).
memory_posix = root / "tools/rexglue/src/core/memory_posix.cpp"
memory_text = memory_posix.read_text()
mach_include = """#if REX_PLATFORM_MAC
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach/vm_region.h>
#endif  // REX_PLATFORM_MAC
"""
mach_include_ios = """#if REX_PLATFORM_MAC && !REX_PLATFORM_IOS
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach/vm_region.h>
#endif  // REX_PLATFORM_MAC && !REX_PLATFORM_IOS
"""
assert memory_text.count(mach_include) == 1, "unexpected ReXGlue Mach VM include block"
memory_text = memory_text.replace(mach_include, mach_include_ios)
query_start = "bool QueryProtect(void* base_address, size_t& length, PageAccess& access_out) {\n#if REX_PLATFORM_MAC\n"
query_start_ios = "bool QueryProtect(void* base_address, size_t& length, PageAccess& access_out) {\n#if REX_PLATFORM_MAC && !REX_PLATFORM_IOS\n"
assert memory_text.count(query_start) == 1, "unexpected ReXGlue QueryProtect implementation"
memory_text = memory_text.replace(query_start, query_start_ios)
memory_posix.write_text(memory_text)

# SDL3 has distinct Cocoa (macOS) and UIKit (iOS) video drivers. This target
# intentionally keeps REX_PLATFORM_MAC for the shared CAMetalLayer surface,
# but must never inherit the macOS-only Cocoa driver selection.
window_context = root / "tools/rexglue/src/ui/windowed_app_context_sdl.cpp"
window_context_text = window_context.read_text()
driver_needle = """#if REX_PLATFORM_MAC
  // macOS presents via a CAMetalLayer surface obtained from the Cocoa driver.
  if (requested_driver.empty()) {
    requested_driver = "cocoa";
  }
#endif"""
driver_replacement = """#if REX_PLATFORM_IOS
  // ASURA_IOS_SDL_UIKIT_DRIVER_V1: iOS must use SDL's UIKit video backend.
  // Selecting Cocoa makes SDL_InitSubSystem(SDL_INIT_VIDEO) fail before the
  // ReXApp window and native launcher can ever be created.
  if (requested_driver.empty()) {
    requested_driver = "uikit";
  }
#elif REX_PLATFORM_MAC
  // macOS presents via a CAMetalLayer surface obtained from the Cocoa driver.
  if (requested_driver.empty()) {
    requested_driver = "cocoa";
  }
#endif"""
assert window_context_text.count(driver_needle) == 1, "unexpected SDL Apple video-driver selection"
window_context.write_text(window_context_text.replace(driver_needle, driver_replacement))
print("ASURA_IOS_SDL_UIKIT_DRIVER_PATCH_OK")


# The upstream Apple RPATH list is colon-joined, which ld64 records as one
# invalid LC_RPATH. iOS must use only bundle-relative paths; runtime dylibs
# are staged into the app's Frameworks directory by the workflow.
app_cmake = root / "CMakeLists.txt"
app_text = app_cmake.read_text()
bad_rpath = '''elseif(APPLE)
  target_link_options(asura_wrath_recomp PRIVATE "-Wl,-rpath,${REXSDK_DIR}/out/${REX_PLATFORM}:@executable_path/../../../tools/rexglue/out/${REX_PLATFORM}:@executable_path")
'''
good_rpath = '''elseif(APPLE AND CMAKE_SYSTEM_NAME STREQUAL "iOS")
  target_link_options(asura_wrath_recomp PRIVATE "-Wl,-rpath,@executable_path/Frameworks")
elseif(APPLE)
  target_link_options(asura_wrath_recomp PRIVATE "-Wl,-rpath,${REXSDK_DIR}/out/${REX_PLATFORM}:@executable_path/../../../tools/rexglue/out/${REX_PLATFORM}:@executable_path")
'''
assert app_text.count(bad_rpath) == 1, "unexpected upstream Apple RPATH block"
app_cmake.write_text(app_text.replace(bad_rpath, good_rpath))

print("ASURA_IOS_MACH_VM_GUARD_OK")

print("ASURA_IOS_CMAKE_PATCH_OK")
