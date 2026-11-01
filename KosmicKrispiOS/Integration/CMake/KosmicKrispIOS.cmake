# Include after creating an iOS app target.
# include(KosmicKrispIOS.cmake); kosmickrisp_ios_link(MyApp)
function(kosmickrisp_ios_link target)
  if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "KosmicKrispiOS is an iOS-only Vulkan ICD")
  endif()
  get_filename_component(_kk_root "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
  set(_kk_archive "${_kk_root}/build/libkk-kosmickrisp-ios-arm64.a")
  if(NOT EXISTS "${_kk_archive}")
    message(FATAL_ERROR "Missing ${_kk_archive}; run KosmicKrispiOS/build.sh first")
  endif()
  target_sources(${target} PRIVATE
    "${_kk_root}/Integration/Static/KosmicKrispStaticICDBridge.c"
    "${_kk_root}/Integration/Static/KosmicKrispProbe.c")
  target_include_directories(${target} PRIVATE "${_kk_root}/build/include")
  target_link_options(${target} PRIVATE "-Wl,-force_load,${_kk_archive}" "-Wl,-undefined,dynamic_lookup")
  target_link_libraries(${target} PRIVATE
    "-framework Metal" "-framework QuartzCore" "-framework UIKit"
    "-framework Foundation" "-framework CoreGraphics")
endfunction()
