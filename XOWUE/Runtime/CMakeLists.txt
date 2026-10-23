cmake_minimum_required(VERSION 3.26)
project(XOWUEEngine LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)

if(NOT DEFINED XENONRECOMP_ROOT)
    message(FATAL_ERROR "Pass -DXENONRECOMP_ROOT=/path/to/XenonRecomp")
endif()
get_filename_component(XENONRECOMP_ROOT "${XENONRECOMP_ROOT}" ABSOLUTE)
set(PPC_DIR "${CMAKE_CURRENT_LIST_DIR}/../generated/ppc")
set(RECOMP_LOG "${CMAKE_CURRENT_LIST_DIR}/../generated/config/XOWUE-recompile.log")
if(NOT EXISTS "${PPC_DIR}/ppc_recomp_shared.h")
    message(FATAL_ERROR "Missing AOT source tree at ${PPC_DIR}; unpack XOWUE-AOT-source.tar.gz first")
endif()
if(NOT EXISTS "${RECOMP_LOG}")
    message(FATAL_ERROR "Missing XOWUE-recompile.log")
endif()

find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(GENERATED_RUNTIME_DIR "${CMAKE_CURRENT_BINARY_DIR}/runtime-generated")
set(IMPORT_STUBS "${GENERATED_RUNTIME_DIR}/XOWUEImportStubs.cpp")
execute_process(
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_LIST_DIR}/generate_runtime_stubs.py"
            --ppc-dir "${PPC_DIR}" --recompile-log "${RECOMP_LOG}" --output "${IMPORT_STUBS}"
    RESULT_VARIABLE STUB_RESULT
)
if(NOT STUB_RESULT EQUAL 0)
    message(FATAL_ERROR "Could not generate runtime stubs")
endif()

# XenonUtils contains the upstream XEX2 loader, LZX decompressor and import parser.
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Use static third-party libraries" FORCE)
set(THIRDPARTY_ROOT "${XENONRECOMP_ROOT}/thirdparty")
add_subdirectory("${THIRDPARTY_ROOT}" "${CMAKE_CURRENT_BINARY_DIR}/xenon-thirdparty")
add_subdirectory("${XENONRECOMP_ROOT}/XenonUtils" "${CMAKE_CURRENT_BINARY_DIR}/xenon-utils")

file(GLOB PPC_SOURCES CONFIGURE_DEPENDS "${PPC_DIR}/ppc_recomp.*.cpp")
list(LENGTH PPC_SOURCES PPC_SOURCE_COUNT)
if(NOT PPC_SOURCE_COUNT EQUAL 344)
    message(FATAL_ERROR "Expected 344 generated function units plus ppc_func_mapping.cpp, found ${PPC_SOURCE_COUNT} function units")
endif()
add_library(XOWUEEngine STATIC
    XOWUEEngine.cpp
    "${IMPORT_STUBS}"
    "${PPC_DIR}/ppc_func_mapping.cpp"
    ${PPC_SOURCES}
)
target_include_directories(XOWUEEngine PUBLIC
    "${CMAKE_CURRENT_LIST_DIR}"
    "${PPC_DIR}"
    "${XENONRECOMP_ROOT}/XenonUtils"
    "${THIRDPARTY_ROOT}/simde"
)
target_link_libraries(XOWUEEngine PUBLIC XenonUtils)
target_compile_options(XOWUEEngine PRIVATE
    $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-O1>
    $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-fno-strict-aliasing>
    $<$<CXX_COMPILER_ID:AppleClang,Clang>:-Wno-pass-failed>
)
set_target_properties(XOWUEEngine PROPERTIES POSITION_INDEPENDENT_CODE ON)

option(XOWUE_BUILD_HOST_SMOKE "Build a host-side XEX parser smoke test" OFF)
if(XOWUE_BUILD_HOST_SMOKE)
    add_executable(XOWUEHostSmoke HostSmoke.cpp)
    target_link_libraries(XOWUEHostSmoke PRIVATE XOWUEEngine)
    if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
        target_link_options(XOWUEHostSmoke PRIVATE -rdynamic)
    endif()
endif()
