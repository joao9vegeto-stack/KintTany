# Include after creating an iOS app target.
# include(KosmicKrispIOS.cmake); kosmickrisp_ios_link(MyApp)
function(kosmickrisp_ios_link target)
  if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "KosmicKrispiOS is an iOS-only Vulkan ICD")
  endif()
  # Resolve relative to this module, not the caller's CMakeLists.txt.
  get_filename_component(_kk_root "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../.." ABSOLUTE)
  set(_kk_build "${_kk_root}/build/build-ios")
  if(NOT EXISTS "${_kk_build}")
    message(FATAL_ERROR "Missing ${_kk_build}; run KosmicKrispiOS/build.sh first")
  endif()
  file(GLOB_RECURSE _kk_archives CONFIGURE_DEPENDS "${_kk_build}/*.a")
  list(FILTER _kk_archives EXCLUDE REGEX "libkk-ios-smoke-objects\.a$")
  if(NOT _kk_archives)
    message(FATAL_ERROR "No KosmicKrisp iOS static archives found under ${_kk_build}")
  endif()
  target_sources(${target} PRIVATE
    "${_kk_root}/Integration/Static/KosmicKrispStaticICDBridge.c"
    "${_kk_root}/Integration/Static/KosmicKrispProbe.c")
  target_include_directories(${target} PRIVATE "${_kk_root}/build/include")
  foreach(_kk_archive IN LISTS _kk_archives)
    target_link_options(${target} PRIVATE "-Wl,-force_load,${_kk_archive}")
  endforeach()
  target_link_options(${target} PRIVATE "-Wl,-u,_vk_icdGetInstanceProcAddr")
  target_link_libraries(${target} PRIVATE
    "-framework Metal" "-framework QuartzCore" "-framework UIKit"
    "-framework Foundation" "-framework CoreGraphics" "-lc++" "-lz")
endfunction()
