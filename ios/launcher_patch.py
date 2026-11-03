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

header=root/"src/asurawrath_app.h"
text=header.read_text()
marker="// ASURA_IOS_PLAY_GATE_V1"
if marker in text: raise SystemExit("native Play gate already applied")
text=text.replace('#include <rex/rex_app.h>','#include <rex/rex_app.h>\n#include "asura_ios_native.h"\n#include <functional>\n#include <optional>\n#include <string>\n#include <vector>\n#include <dispatch/dispatch.h>\n#include <stdexcept>')
# Preserve the upstream Android setup hook and instrument it in place.
setup_hook='  void OnPostSetup() override {'
if text.count(setup_hook)!=1:
    raise SystemExit(f"expected exactly one upstream OnPostSetup hook, found {text.count(setup_hook)}")
text=text.replace(setup_hook, setup_hook+'\n    AsuraIOSLog("HOOK OnPostSetup");', 1)
code=r"""
#ifndef ASURA_IOS_BUILD_NUMBER
#define ASURA_IOS_BUILD_NUMBER "1"
#endif
namespace {
std::filesystem::path ResolveAsuraGameRoot(const std::filesystem::path&p){std::error_code ec;if(p.empty()||!std::filesystem::is_directory(p,ec))return {};if(std::filesystem::is_regular_file(p/"default.xex",ec))return p;if(std::filesystem::is_regular_file(p/"BCGame"/"default.xex",ec))return p/"BCGame";if(std::filesystem::is_regular_file(p/"extracted"/"default.xex",ec))return p/"extracted";if(std::filesystem::is_regular_file(p/"extracted"/"BCGame"/"default.xex",ec))return p/"extracted"/"BCGame";return {};}
std::filesystem::path FindAsuraGameRoot(const rex::PathConfig&paths){auto docs=std::filesystem::path(AsuraIOSDocumentsPath());auto user=paths.user_data_root;auto bundle=rex::filesystem::GetExecutableFolder();std::vector<std::filesystem::path>roots={paths.game_data_root,docs,docs/"Asura's Wrath",docs/"AsurasWrath",docs/"Asura",docs/"Game",docs/"Games",user,user/"Asura's Wrath",bundle,bundle/"Asura's Wrath",bundle.parent_path(),std::filesystem::current_path()};for(const auto&p:roots){auto f=ResolveAsuraGameRoot(p);if(!f.empty())return f;}std::error_code ec;for(const auto&p:{docs,user})if(!p.empty()&&std::filesystem::is_directory(p,ec))for(std::filesystem::directory_iterator i(p,ec),e;i!=e&&!ec;i.increment(ec))if(i->is_directory(ec)){auto f=ResolveAsuraGameRoot(i->path());if(!f.empty())return f;}return {};}
std::filesystem::path FindAsuraGameRootForLauncher(){auto docs=std::filesystem::path(AsuraIOSDocumentsPath());std::vector<std::filesystem::path>roots={docs,docs/"Asura's Wrath",docs/"AsurasWrath",docs/"Asura",docs/"Game",docs/"Games"};for(const auto&p:roots){auto f=ResolveAsuraGameRoot(p);if(!f.empty())return f;}std::error_code ec;if(std::filesystem::is_directory(docs,ec))for(std::filesystem::directory_iterator i(docs,ec),e;i!=e&&!ec;i.increment(ec))if(i->is_directory(ec)){auto f=ResolveAsuraGameRoot(i->path());if(!f.empty())return f;}return {};}
std::string g_asura_ios_selected_game_root;
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
 void OnShutdown() override { AsuraIOSLog("HOOK OnShutdown"); }
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
header.write_text(text)
print("ASURA_IOS_PRE_REXAPP_PLAY_GATE_V1_OK")
