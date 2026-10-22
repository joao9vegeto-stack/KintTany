cmake_minimum_required(VERSION 3.24)
project(PoPTST_Retail LANGUAGES C CXX OBJC OBJCXX)
if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "PoPTST runtime must be compiled for iOS (iphoneos arm64)")
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(RESOT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../repop" CACHE PATH "Pinned rePOP reSOT checkout")
get_filename_component(RESOT_ROOT "${RESOT_ROOT}" ABSOLUTE)
set(RT "${RESOT_ROOT}/port/third_party/xboxrecomp/src")
set(NATIVE_SHADERS "${CMAKE_CURRENT_LIST_DIR}/../../deps/shaders" CACHE PATH "DXC SPIR-V output")
set(SDL_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../../deps/SDL" CACHE PATH "Patched SDL3 source")
set(VULKAN_HEADERS "${CMAKE_CURRENT_LIST_DIR}/../../deps/Vulkan-Headers/include" CACHE PATH "Vulkan-Headers")
foreach(p "${RT}/kernel/nv2a_pb_exec.c" "${NATIVE_SHADERS}/nv2a_native_shaders.h" "${SDL_SOURCE}/CMakeLists.txt" "${VULKAN_HEADERS}/vulkan/vulkan.h")
    if(NOT EXISTS "${p}")
        message(FATAL_ERROR "Missing required real runtime dependency: ${p}")
    endif()
endforeach()
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
set(SDL_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SDL_GPU ON CACHE BOOL "" FORCE)
set(SDL_VULKAN ON CACHE BOOL "" FORCE)
set(CMAKE_INCLUDE_PATH "${VULKAN_HEADERS}" CACHE STRING "" FORCE)
include_directories(SYSTEM "${VULKAN_HEADERS}")
add_subdirectory("${SDL_SOURCE}" "${CMAKE_BINARY_DIR}/sdl" EXCLUDE_FROM_ALL)

# This is the exact, pinned upstream GLSL->SPIR-V optimizer used by Vulkan
# shader-specialization and dynamic NV2A vertex programs.
add_subdirectory("${RESOT_ROOT}/port/render" "${CMAKE_BINARY_DIR}/shader-compiler")
set(RESOT_GUEST_FLAGS -fwrapv -fsigned-char -ffp-contract=off -fno-strict-aliasing)
set(RUNTIME_SOURCES
    ${RT}/platform/win32_compat.c
    ${RT}/kernel/kernel_path.c ${RT}/kernel/kernel_pool.c ${RT}/kernel/kernel_rtl.c
    ${RT}/kernel/kernel_memory.c ${RT}/kernel/kernel_file.c ${RT}/kernel/kernel_thread.c
    ${RT}/kernel/kernel_sync.c ${RT}/kernel/kernel_hal.c ${RT}/kernel/kernel_xbox.c
    ${RT}/kernel/kernel_ob.c ${RT}/kernel/kernel_io.c ${RT}/kernel/kernel_crypto.c
    ${RT}/kernel/kernel_thunks.c ${RT}/kernel/kernel_bridge.c ${RT}/kernel/xbox_memory_layout.c
    ${RT}/kernel/guest_vmem.c ${RT}/kernel/icall_feedback.c ${RT}/kernel/recomp_trace.c
    ${RT}/kernel/nv2a_pb_scan.c ${RT}/kernel/nv2a_pb_exec.c ${RT}/kernel/nv2a_vsh_interp.c
    ${RT}/kernel/nv2a_combiner.c
    ${RT}/audio/dsound_device.c ${RT}/audio/wma_decoder.c
    ${RT}/apu/apu_core.c ${RT}/apu/apu_vp.c ${RT}/apu/apu_dsp.c ${RT}/apu/apu_mmio_hook.c
    ${RT}/usb/ohci.c ${RT}/usb/usb_gamepad.c
    ${RT}/video/video_player.c ${RT}/video/video_pump.c ${RT}/video/fb_present.c)
set(HOST_SOURCES
    "${CMAKE_CURRENT_LIST_DIR}/Native/poptst_engine.c"
    "${CMAKE_CURRENT_LIST_DIR}/Native/poptst_ios_fault.c"
    "${CMAKE_CURRENT_LIST_DIR}/Native/audio_ios.c"
    "${CMAKE_CURRENT_LIST_DIR}/Native/font_ios.m"
    "${CMAKE_CURRENT_LIST_DIR}/Native/poptst_touch_overlay.m"
    "${RESOT_ROOT}/port/ios/generated_input_ios.c"
    "${RESOT_ROOT}/port/android/src/host_files.c"
    "${RESOT_ROOT}/port/android/src/sha256.c"
    "${RESOT_ROOT}/port/android/src/options_android.c"
    "${RESOT_ROOT}/port/windows/src/scene.c"
    "${RESOT_ROOT}/port/game/recomp_manual.c"
    "${CMAKE_CURRENT_LIST_DIR}/Runtime/poptst_retail_boot.c")
# B24.1: the UIKit HUD owns weak window references; this Objective-C file
# must opt into ARC for __weak to be valid on iPhoneOS. Keep the guest
# runtime's C/C++ files under their existing non-ARC build flags.
set_source_files_properties("${CMAKE_CURRENT_LIST_DIR}/Native/poptst_touch_overlay.m"
    PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
file(GLOB_RECURSE GEN CONFIGURE_DEPENDS "${RESOT_ROOT}/source/xbox-retail/gen/*.c")
list(LENGTH GEN GEN_COUNT)
if(GEN_COUNT LESS 70)
    message(FATAL_ERROR "Real retail static recompilation unavailable (${GEN_COUNT} C files)")
endif()
add_library(PoPTSTRetail SHARED ${RUNTIME_SOURCES} ${HOST_SOURCES}
    "${RESOT_ROOT}/source/xbox-retail/target_hooks.c" ${GEN})
target_compile_definitions(PoPTSTRetail PRIVATE POPTST_FAIL_CLOSED_LIFT=1 RESOT_RUNTIME_RETAIL=1
    RESOT_DEFAULT_ASPECT=\"16:9\" _GNU_SOURCE)
target_include_directories(PoPTSTRetail PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/Runtime"
    "${CMAKE_CURRENT_LIST_DIR}/Native"
    "${RESOT_ROOT}/port/android/compat"
    "${RESOT_ROOT}/port/android/src"
    "${RESOT_ROOT}/port/third_party/xboxrecomp/include/xbox"
    "${RESOT_ROOT}/source/xbox-retail"
    "${RESOT_ROOT}/source/xbox-retail/gen"
    "${RT}" "${RT}/platform" "${RT}/kernel" "${RT}/nv2a"
    "${RT}/apu" "${RT}/usb" "${RT}/input" "${RT}/audio"
    "${RT}/video" "${RT}/d3d" "${NATIVE_SHADERS}"
    "${RESOT_ROOT}/port/render")
# The pinned upstream manual override file uses ptrdiff_t without including
# <stddef.h>. Preinclude the standard type header consistently for iOS C.
target_compile_options(PoPTSTRetail PRIVATE ${RESOT_GUEST_FLAGS} -O2 -w -include stddef.h)
target_link_libraries(PoPTSTRetail PRIVATE SDL3::SDL3-static resot_shader_compiler
    "-framework Foundation" "-framework UIKit" "-framework QuartzCore"
    "-framework Metal" "-framework CoreGraphics" "-framework GameController")
set_target_properties(PoPTSTRetail PROPERTIES
    INSTALL_NAME_DIR "@rpath" OUTPUT_NAME "PoPTSTRetail"
    XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO")
target_link_options(PoPTSTRetail PRIVATE "-Wl,-undefined,error")
