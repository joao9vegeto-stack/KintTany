from pathlib import Path
import shutil

root=Path(__file__).resolve().parents[1]/"upstream"
# asurawrath_app.h is compiled from upstream/src and includes this header
# with quotes; stage the iOS interface beside it before patching/building.
native_header=Path(__file__).resolve().with_name("asura_ios_native.h")
staged_header=root/"src"/"asura_ios_native.h"
if not native_header.is_file():
    raise SystemExit(f"missing iOS native interface: {native_header}")
shutil.copy2(native_header, staged_header)
if staged_header.read_bytes()!=native_header.read_bytes():
    raise SystemExit("failed to stage asura_ios_native.h into upstream/src")
print(f"ASURA_IOS_NATIVE_HEADER_STAGED={staged_header}")

# REX_PLATFORM_MAC is true for both macOS and iOS in TargetConditionals.
# Define a distinct iOS flag so SDL chooses UIKit and Vulkan skips macOS
# MoltenVK discovery while retaining the shared Metal surface code.
platform_header = root / "tools/rexglue/include/rex/platform.h"
platform_text = platform_header.read_text()
platform_marker = "ASURA_IOS_PLATFORM_MACROS_V1"
if platform_marker not in platform_text:
    old_platform = """#if defined(TARGET_OS_MAC) && TARGET_OS_MAC
#define REX_PLATFORM_MAC 1"""
    new_platform = """#if defined(TARGET_OS_IPHONE) && TARGET_OS_IPHONE
#define REX_PLATFORM_IOS 1
#define REX_PLATFORM_MAC 1
#elif defined(TARGET_OS_MAC) && TARGET_OS_MAC
#define REX_PLATFORM_MAC 1"""
    if platform_text.count(old_platform) != 1:
        raise SystemExit("unexpected ReXGlue Apple platform detection")
    platform_text = platform_text.replace(old_platform, new_platform, 1)
    ios_default_anchor = """#ifndef REX_PLATFORM_MAC
#define REX_PLATFORM_MAC 0
#endif"""
    if platform_text.count(ios_default_anchor) != 1:
        raise SystemExit("unexpected ReXGlue platform macro defaults")
    platform_text = platform_text.replace(ios_default_anchor, ios_default_anchor + """
#ifndef REX_PLATFORM_IOS
#define REX_PLATFORM_IOS 0
#endif
// ASURA_IOS_PLATFORM_MACROS_V1
""", 1)
    platform_header.write_text(platform_text)
    print("ASURA_IOS_PLATFORM_MACROS_V1_OK")


header=root/"src/asurawrath_app.h"
text=header.read_text()
marker="// ASURA_IOS_PLAY_GATE_V1"
if marker in text: raise SystemExit("native Play gate already applied")
text=text.replace('#include <rex/rex_app.h>','#include <rex/rex_app.h>\n#include "asura_ios_native.h"\n#include <functional>\n#include <optional>\n#include <string>\n#include <vector>\n#include <dispatch/dispatch.h>\n#include <stdexcept>')
# Preserve the upstream Android setup hook and instrument it in place.
setup_hook='  void OnPostSetup() override {'
if text.count(setup_hook)!=1:
    raise SystemExit(f"expected exactly one upstream OnPostSetup hook, found {text.count(setup_hook)}")
text=text.replace(setup_hook, setup_hook+'\n#if defined(__APPLE__)\n    AsuraIOSLog("HOOK OnPostSetup");\n#endif', 1)
code=r"""
#ifndef ASURA_IOS_BUILD_NUMBER
#define ASURA_IOS_BUILD_NUMBER "1"
#endif
namespace {
std::filesystem::path ResolveAsuraGameRoot(const std::filesystem::path&p){std::error_code ec;if(p.empty()||!std::filesystem::is_directory(p,ec))return {};if(std::filesystem::is_regular_file(p/"default.xex",ec))return p;if(std::filesystem::is_regular_file(p/"BCGame"/"default.xex",ec))return p/"BCGame";if(std::filesystem::is_regular_file(p/"extracted"/"default.xex",ec))return p/"extracted";if(std::filesystem::is_regular_file(p/"extracted"/"BCGame"/"default.xex",ec))return p/"extracted"/"BCGame";return {};}
std::filesystem::path FindAsuraGameRoot(const rex::PathConfig&paths){auto docs=std::filesystem::path(AsuraIOSDocumentsPath());auto user=paths.user_data_root;auto bundle=rex::GetExecutableFolder();std::vector<std::filesystem::path>roots={paths.game_data_root,docs,docs/"Asura's Wrath",docs/"AsurasWrath",docs/"Asura",docs/"Game",docs/"Games",user,user/"Asura's Wrath",bundle,bundle/"Asura's Wrath",bundle.parent_path(),std::filesystem::current_path()};for(const auto&p:roots){auto f=ResolveAsuraGameRoot(p);if(!f.empty())return f;}std::error_code ec;for(const auto&p:{docs,user})if(!p.empty()&&std::filesystem::is_directory(p,ec))for(std::filesystem::directory_iterator i(p,ec),e;i!=e&&!ec;i.increment(ec))if(i->is_directory(ec)){auto f=ResolveAsuraGameRoot(i->path());if(!f.empty())return f;}return {};}
std::filesystem::path FindAsuraGameRootForLauncher(){auto docs=std::filesystem::path(AsuraIOSDocumentsPath());std::vector<std::filesystem::path>roots={docs,docs/"Asura's Wrath",docs/"AsurasWrath",docs/"Asura",docs/"Game",docs/"Games"};for(const auto&p:roots){auto f=ResolveAsuraGameRoot(p);if(!f.empty())return f;}std::error_code ec;if(std::filesystem::is_directory(docs,ec))for(std::filesystem::directory_iterator i(docs,ec),e;i!=e&&!ec;i.increment(ec))if(i->is_directory(ec)){auto f=ResolveAsuraGameRoot(i->path());if(!f.empty())return f;}return {};}
std::string g_asura_ios_selected_game_root;
// First guest-frame readiness is tracked by the native iOS host.
}
"""
text=text.replace("class AsurawrathApp : public rex::ReXApp {",code+"\n"+marker+"\nclass AsurawrathApp : public rex::ReXApp {")
create_old = """    return std::unique_ptr<AsurawrathApp>(
        new AsurawrathApp(ctx, "asura_wrath_recomp", PPCImageConfig));"""
create_new = """#if defined(__APPLE__)
    // ASURA_IOS_PLAY_GATE_V1: the launcher is the first screen. Do not
    // construct ReXApp until the user explicitly taps Play.
    const auto detected = FindAsuraGameRootForLauncher();
    auto selected = AsuraIOSWaitForGameSelection(
        detected.string(), [] { return FindAsuraGameRootForLauncher().string(); });
    if (selected.empty()) {
      AsuraIOSLog("APP_LAUNCH_GATE_ABORTED_EMPTY_GAME_PATH");
      return nullptr;
    }
    g_asura_ios_selected_game_root = std::move(selected);
#endif
    return std::unique_ptr<AsurawrathApp>(
        new AsurawrathApp(ctx, "asura_wrath_recomp", PPCImageConfig));"""
if text.count(create_old) != 1:
    raise SystemExit(f"expected one ReXApp factory body, found {text.count(create_old)}")
text = text.replace(create_old, create_new, 1)
configure_old = "  void OnConfigurePaths(rex::PathConfig &paths) override {"
configure_new = """  void OnConfigurePaths(rex::PathConfig &paths) override {
#if defined(__APPLE__)
    AsuraIOSLog("HOOK OnConfigurePaths");
    if (!g_asura_ios_selected_game_root.empty()) {
      paths.game_data_root = g_asura_ios_selected_game_root;
      AsuraIOSLog("PLAY_GATE_GAME_PATH " + g_asura_ios_selected_game_root);
    }
#endif"""
if text.count(configure_old) != 1:
    raise SystemExit("expected exactly one upstream OnConfigurePaths")
text = text.replace(configure_old, configure_new, 1)
method=r"""
 void OnPostInitLogging() override { AsuraIOSLog("HOOK OnPostInitLogging"); }
 void OnPostLoadXexImage() override { AsuraIOSLog("HOOK OnPostLoadXexImage"); }
 void OnPreLaunchModule() override { AsuraIOSLog("HOOK OnPreLaunchModule"); }
 void OnShutdown() override { AsuraIOSLog("HOOK OnShutdown"); if (!AsuraIOSHasPresentedFrame()) AsuraIOSSetLauncherStatus("A APRESENTAÇÃO GRÁFICA NÃO INICIOU. Consulte Documents/log.txt"); }
"""
start=text.find("class AsurawrathApp : public rex::ReXApp {");end=text.rfind("\n};")
if start<0 or end<start or text[end+3:].strip():raise SystemExit("AsurawrathApp terminator not found")
text=text[:end]+"\n"+method+text[end:]
if "ASURA_IOS_PLAY_GATE_V1" not in text or "AsuraIOSWaitForGameSelection" not in text:
    raise SystemExit("missing pre-ReXApp Play gate")
if "OnFinalizePaths(" in text:
    raise SystemExit("legacy post-presentation launcher must not be generated")
if text.count("void OnConfigurePaths(rex::PathConfig &paths) override") != 1:
    raise SystemExit("expected exactly one OnConfigurePaths override")
# iOS must load the bundled ICD adapter, not macOS MoltenVK discovery.
vulkan_instance = root / "tools/rexglue/src/ui/vulkan/vulkan_instance.cpp"
vulkan_text = vulkan_instance.read_text()
vulkan_text, n1 = __import__("re").subn(
    r'#if REX_PLATFORM_MAC\n#include "vulkan_moltenvk.h"\n#endif',
    '#if REX_PLATFORM_MAC && !REX_PLATFORM_IOS\n#include "vulkan_moltenvk.h"\n#endif',
    vulkan_text, count=1)
if n1 != 1:
    raise SystemExit("unexpected Vulkan MoltenVK include guard")
vulkan_text, n2 = __import__("re").subn(
    r'#if REX_PLATFORM_MAC\n  const MacOSVulkanRuntimePaths',
    '#if REX_PLATFORM_MAC && !REX_PLATFORM_IOS\n  const MacOSVulkanRuntimePaths',
    vulkan_text, count=1)
if n2 != 1:
    raise SystemExit("unexpected Vulkan macOS loader branch")
vulkan_text = vulkan_text.replace("#include <rex/cvar.h>", "#include <rex/cvar.h>\n#include <rex/filesystem.h>", 1)
ios_loader_anchor = """  if (!loader_loaded) {
    loader_loaded = vulkan_instance->loader_.Load(platform::lib_names::kVulkanLoader);
  }"""
ios_loader_replacement = """#if REX_PLATFORM_IOS
  const auto ios_loader_path = rex::GetExecutableFolder() / "Frameworks" / "libvulkan.dylib";
  loader_loaded = vulkan_instance->loader_.Load(ios_loader_path);
  if (loader_loaded) {
    REXLOG_INFO("Loaded bundled iOS Vulkan ICD bridge from {}", ios_loader_path.string());
  } else {
    REXLOG_ERROR("Failed to load bundled iOS Vulkan ICD bridge at {}", ios_loader_path.string());
  }
#endif
  if (!loader_loaded) {
    loader_loaded = vulkan_instance->loader_.Load(platform::lib_names::kVulkanLoader);
  }"""
if vulkan_text.count(ios_loader_anchor) != 1:
    raise SystemExit("unexpected Vulkan generic loader fallback")
vulkan_text = vulkan_text.replace(ios_loader_anchor, ios_loader_replacement, 1)
vulkan_instance.write_text(vulkan_text)
print("ASURA_IOS_VULKAN_ICD_BRIDGE_LOADER_PATCH_OK")
print("ASURA_IOS_VULKAN_ICD_BUNDLE_PATH_V1_OK")


# ASURA_IOS_FIRST_PRESENT_GATE_V1: preserve the native launcher until the
# ReXGlue Vulkan presenter confirms a successful presentation of guest output.
instance_include = '#include <rex/ui/vulkan/presenter.h>'
instance_add = instance_include + '''
#if REX_PLATFORM_IOS
#include "../../../../../src/asura_ios_native.h"
#endif'''
if vulkan_text.count(instance_include) != 1:
    raise SystemExit("unexpected Vulkan instance include layout")
vulkan_text = vulkan_text.replace(instance_include, instance_add, 1)
vulkan_text = vulkan_text.replace(
    '    REXLOG_INFO("Loaded bundled iOS Vulkan ICD bridge from {}", ios_loader_path.string());',
    '    REXLOG_INFO("Loaded bundled iOS Vulkan ICD bridge from {}", ios_loader_path.string());\n'
    '    AsuraIOSLog("VULKAN_LOADER_LOADED " + ios_loader_path.string());', 1)
vulkan_text = vulkan_text.replace(
    '    REXLOG_ERROR("Failed to load bundled iOS Vulkan ICD bridge at {}", ios_loader_path.string());',
    '    REXLOG_ERROR("Failed to load bundled iOS Vulkan ICD bridge at {}", ios_loader_path.string());\n'
    '    AsuraIOSLog("VULKAN_LOADER_FAILED " + ios_loader_path.string());', 1)
vulkan_text = vulkan_text.replace(
    '    REXLOG_ERROR("Failed to get Vulkan loader function pointers");\n    return nullptr;',
    '    REXLOG_ERROR("Failed to get Vulkan loader function pointers");\n'
    '#if REX_PLATFORM_IOS\n'
    '    AsuraIOSLog("VULKAN_LOADER_REQUIRED_EXPORT_MISSING (vkGetInstanceProcAddr/vkDestroyInstance)");\n'
    '#endif\n'
    '    return nullptr;', 1)
vulkan_text = vulkan_text.replace(
    '  // If enabled layers are not present, will disable all extensions provided by\n'
    '  // the layers by truncating the enabled extension vector to this size.',
    '#if REX_PLATFORM_IOS\n'
    '  AsuraIOSLog("VULKAN_INSTANCE_EXTENSIONS surface=" +\n'
    '              std::to_string(vulkan_instance->extensions_.ext_KHR_surface) +\n'
    '              " metal=" + std::to_string(vulkan_instance->extensions_.ext_EXT_metal_surface) +\n'
    '              " portability=" +\n'
    '              std::to_string(vulkan_instance->extensions_.ext_KHR_portability_enumeration));\n'
    '  if (with_surface && (!vulkan_instance->extensions_.ext_KHR_surface ||\n'
    '                       !vulkan_instance->extensions_.ext_EXT_metal_surface)) {\n'
    '    AsuraIOSLog("VULKAN_REQUIRED_METAL_SURFACE_EXTENSION_MISSING");\n'
    '    return nullptr;\n'
    '  }\n'
    '#endif\n\n'
    '  // If enabled layers are not present, will disable all extensions provided by\n'
    '  // the layers by truncating the enabled extension vector to this size.', 1)
vulkan_text = vulkan_text.replace(
    '  // Load instance functions.',
    '#if REX_PLATFORM_IOS\n'
    '  AsuraIOSLog("VULKAN_INSTANCE_CREATED");\n'
    '#endif\n\n'
    '  // Load instance functions.', 1)
vulkan_text = vulkan_text.replace(
    '  // Log instance properties.',
    '#if REX_PLATFORM_IOS\n'
    '  AsuraIOSLog("VULKAN_INSTANCE_READY");\n'
    '#endif\n\n'
    '  // Log instance properties.', 1)
if 'AsuraIOSLog("VULKAN_INSTANCE_READY")' not in vulkan_text:
    raise SystemExit("failed to instrument Vulkan instance")
vulkan_instance.write_text(vulkan_text)

presenter = root / "tools/rexglue/src/ui/vulkan/vulkan_presenter.cpp"
presenter_text = presenter.read_text()
presenter_marker = "ASURA_IOS_FIRST_PRESENT_GATE_V1"
if presenter_marker not in presenter_text:
    presenter_include = '#include <rex/ui/vulkan/presenter.h>'
    presenter_add = presenter_include + '''
#if REX_PLATFORM_IOS
#include "../../../../../src/asura_ios_native.h"
// ASURA_IOS_FIRST_PRESENT_GATE_V1
#endif'''
    if presenter_text.count(presenter_include) != 1:
        raise SystemExit("unexpected Vulkan presenter include layout")
    presenter_text = presenter_text.replace(presenter_include, presenter_add, 1)
    function_anchor = 'Presenter::PaintResult VulkanPresenter::PaintAndPresentImpl(bool execute_ui_drawers) {'
    function_replacement = function_anchor + '\n  bool asura_guest_frame_rendered = false;'
    if presenter_text.count(function_anchor) != 1:
        raise SystemExit("unexpected Vulkan presenter paint function")
    presenter_text = presenter_text.replace(function_anchor, function_replacement, 1)
    guest_draw_anchor = '''      if (guest_output_flow.effect_count) {
        // Actually draw the guest output.'''
    guest_draw_replacement = '''      if (guest_output_flow.effect_count) {
#if REX_PLATFORM_IOS
        asura_guest_frame_rendered = true;
#endif
        // Actually draw the guest output.'''
    if presenter_text.count(guest_draw_anchor) != 1:
        raise SystemExit("unexpected guest output draw branch")
    presenter_text = presenter_text.replace(guest_draw_anchor, guest_draw_replacement, 1)
    metal_anchor = '''        vulkan_surface_create_result = ifn.vkCreateMetalSurfaceEXT(
            instance, &surface_create_info, nullptr, &paint_context_.vulkan_surface);'''
    metal_replacement = metal_anchor + '''
#if REX_PLATFORM_IOS
        AsuraIOSLog("VULKAN_METAL_SURFACE_CREATE_RESULT=" +
                    std::to_string(vulkan_surface_create_result));
#endif'''
    if presenter_text.count(metal_anchor) != 1:
        raise SystemExit("unexpected Metal surface creation call")
    presenter_text = presenter_text.replace(metal_anchor, metal_replacement, 1)
    swap_anchor = '''    paint_context_.swapchain = PaintContext::CreateSwapchainForVulkanSurface(
        vulkan_device_, paint_context_.vulkan_surface, new_surface_width, new_surface_height,
        VK_NULL_HANDLE, paint_context_.present_queue_family, new_swapchain_format,
        paint_context_.swapchain_extent, paint_context_.swapchain_is_fifo, surface_unusable);'''
    swap_replacement = swap_anchor + '''
#if REX_PLATFORM_IOS
      AsuraIOSLog("VULKAN_SWAPCHAIN_CREATE_RESULT=" +
                  std::to_string(paint_context_.swapchain != VK_NULL_HANDLE) +
                  " extent=" + std::to_string(paint_context_.swapchain_extent.width) + "x" +
                  std::to_string(paint_context_.swapchain_extent.height));
#endif'''
    if presenter_text.count(swap_anchor) != 1:
        raise SystemExit("unexpected initial swapchain creation call")
    presenter_text = presenter_text.replace(swap_anchor, swap_replacement, 1)
    acquire_anchor = '''  VkResult acquire_result =
      dfn.vkAcquireNextImageKHR(device, paint_context_.swapchain, UINT64_MAX, acquire_semaphore,
                                VK_NULL_HANDLE, &swapchain_image_index);'''
    acquire_replacement = acquire_anchor + '''
#if REX_PLATFORM_IOS
  if (acquire_result != VK_SUCCESS && acquire_result != VK_SUBOPTIMAL_KHR) {
    AsuraIOSLog("VULKAN_ACQUIRE_FAILED result=" + std::to_string(acquire_result));
  }
#endif'''
    if presenter_text.count(acquire_anchor) != 1:
        raise SystemExit("unexpected swapchain acquire call")
    presenter_text = presenter_text.replace(acquire_anchor, acquire_replacement, 1)
    submit_anchor = '''    if (submit_result != VK_SUCCESS) {
      REXLOG_ERROR("VulkanPresenter: Failed to submit command buffers");'''
    submit_replacement = '''    if (submit_result != VK_SUCCESS) {
#if REX_PLATFORM_IOS
      AsuraIOSLog("VULKAN_QUEUE_SUBMIT_FAILED result=" + std::to_string(submit_result));
#endif
      REXLOG_ERROR("VulkanPresenter: Failed to submit command buffers");'''
    if (presenter_text.count(submit_anchor) != 1):
        raise SystemExit("unexpected queue submit failure branch")
    presenter_text = presenter_text.replace(submit_anchor, submit_replacement, 1)
    present_anchor = '''  switch (present_result) {
    case VK_SUCCESS:'''
    present_replacement = '''#if REX_PLATFORM_IOS
  if (present_result == VK_SUCCESS || present_result == VK_SUBOPTIMAL_KHR) {
    if (asura_guest_frame_rendered) {
      AsuraIOSNotifyFirstPresent();
    } else {
      static std::atomic<bool> logged_waiting_for_guest_output = false;
      if (!logged_waiting_for_guest_output.exchange(true)) {
        AsuraIOSLog("VULKAN_PRESENT_OK_WAITING_FOR_GUEST_OUTPUT");
      }
    }
  } else {
    AsuraIOSLog("VULKAN_QUEUE_PRESENT_FAILED result=" + std::to_string(present_result));
  }
#endif
  switch (present_result) {
    case VK_SUCCESS:'''
    if (presenter_text.count(present_anchor) != 1):
        raise SystemExit("unexpected queue present result switch")
    presenter_text = presenter_text.replace(present_anchor, present_replacement, 1)
    presenter.write_text(presenter_text)
    print("ASURA_IOS_FIRST_PRESENT_GATE_V1_OK")


# Instrument the exact ReXApp presentation failure branches in Documents/log.txt.
rex_app = root / "tools/rexglue/src/ui/rex_app.cpp"
rex_text = rex_app.read_text()
rex_marker = "ASURA_IOS_REXAPP_PRESENTATION_DIAGNOSTICS_V1"
if rex_marker not in rex_text:
    rex_text = rex_text.replace("#include <rex/rex_app.h>", "#include <rex/rex_app.h>\n#include \"../../../../src/asura_ios_native.h\"\n// " + rex_marker, 1)
    old_init = """  if (!SetupEnvironment())
    return false;
  if (!SetupPresentation())
    return false;"""
    new_init = """  if (!SetupEnvironment()) {
    AsuraIOSLog("REXAPP_SETUP_ENVIRONMENT_FAILED");
    return false;
  }
  AsuraIOSLog("REXAPP_SETUP_ENVIRONMENT_OK");
  if (!SetupPresentation()) {
    AsuraIOSLog("REXAPP_SETUP_PRESENTATION_FAILED");
    return false;
  }
  AsuraIOSLog("REXAPP_SETUP_PRESENTATION_OK");"""
    if rex_text.count(old_init) != 1:
        raise SystemExit("ReXApp OnInitialize sequence changed")
    rex_text = rex_text.replace(old_init, new_init, 1)
    rex_text = rex_text.replace("  OnPreSetup(config_);", "  OnPreSetup(config_);\n  AsuraIOSLog(\"REXAPP_PRESENTATION_BEGIN plugin=\" + config_.gpu_plugin + \" backend=\" + REXCVAR_GET(gpu_backend));", 1)
    rex_text = rex_text.replace("    if (!config_.graphics) {", "    if (!config_.graphics) {\n      AsuraIOSLog(\"REXAPP_GPU_PLUGIN_LOAD_FAILED name=\" + config_.gpu_plugin);", 1)
    rex_text = rex_text.replace("  if (config_.graphics) {\n    X_STATUS status = config_.graphics->SetupPresentation(&app_context());", "  if (config_.graphics) {\n    AsuraIOSLog(\"REXAPP_GPU_PLUGIN_LOAD_OK\");\n    X_STATUS status = config_.graphics->SetupPresentation(&app_context());", 1)
    rex_text = rex_text.replace("    if (XFAILED(status)) {\n      REXLOG_ERROR(\"Graphics presentation setup failed: {:08X}\", status);", "    if (XFAILED(status)) {\n      AsuraIOSLog(\"REXAPP_GRAPHICS_SETUP_FAILED status=\" + std::to_string(status));\n      REXLOG_ERROR(\"Graphics presentation setup failed: {:08X}\", status);", 1)
    rex_text = rex_text.replace("  if (!window_) {\n    REXLOG_ERROR(\"Failed to create window\");", "  if (!window_) {\n    AsuraIOSLog(\"REXAPP_WINDOW_CREATE_FAILED\");\n    REXLOG_ERROR(\"Failed to create window\");", 1)
    rex_text = rex_text.replace("  window_->Open();", "  window_->Open();\n  AsuraIOSLog(\"REXAPP_WINDOW_OPEN_CALLED\");", 1)
    rex_app.write_text(rex_text)
    print("ASURA_IOS_REXAPP_PRESENTATION_DIAGNOSTICS_V1_OK")

header.write_text(text)
print("ASURA_IOS_PRE_REXAPP_PLAY_GATE_V1_OK")
