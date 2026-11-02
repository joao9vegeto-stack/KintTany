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
marker="// ASURA_IOS_NATIVE_LAUNCHER_V4"
if marker in text: raise SystemExit("native launcher already applied")
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
}
"""
text=text.replace("class AsurawrathApp : public rex::ReXApp {",code+"\n"+marker+"\nclass AsurawrathApp : public rex::ReXApp {")
method=r"""
 void OnPostInitLogging() override { AsuraIOSLog("HOOK OnPostInitLogging"); }
 void OnPostLoadXexImage() override { AsuraIOSLog("HOOK OnPostLoadXexImage"); }
 void OnPreLaunchModule() override { AsuraIOSLog("HOOK OnPreLaunchModule"); }
 void OnShutdown() override { AsuraIOSLog("HOOK OnShutdown"); }

 // ReXApp calls OnFinalizePaths only after SetupPresentation has created the
 // SDL/UIKit window and ImGui surface. Returning nullopt keeps the event loop
 // alive while the native folder launcher is visible. The Play callback runs
 // on UIKit's main queue and resumes ReXApp with the selected game path.
 std::optional<rex::PathConfig> OnFinalizePaths(
     const rex::PathConfig& defaults,
     std::function<void(rex::PathConfig)> resume) override {
#if defined(__APPLE__)
   AsuraIOSLog("HOOK OnFinalizePaths BEGIN");
   auto detected = FindAsuraGameRoot(defaults);
   AsuraIOSLog(detected.empty() ? "GAME_DISCOVERY NOT_FOUND" :
               "GAME_DISCOVERY FOUND " + detected.string());
   AsuraIOSShowLauncher(detected.string(),
     [defaults]() { return FindAsuraGameRoot(defaults).string(); },
     [defaults, resume = std::move(resume)](std::string selected) mutable {
       if (selected.empty()) {
         AsuraIOSLog("LAUNCHER_START_REJECTED_EMPTY_PATH");
         return;
       }
       auto paths = defaults;
       paths.game_data_root = std::move(selected);
       AsuraIOSLog("LAUNCHER PATH_ACCEPTED " + paths.game_data_root.string());
       resume(std::move(paths));
     });
   return std::nullopt;
#else
   return defaults;
#endif
 }
"""
start=text.find("class AsurawrathApp : public rex::ReXApp {");end=text.rfind("\n};")
if start<0 or end<start or text[end+3:].strip():raise SystemExit("AsurawrathApp terminator not found")
text=text[:end]+"\n"+method+text[end:];# The launcher belongs to OnFinalizePaths, not OnConfigurePaths:
# ReXApp invokes OnConfigurePaths inside SetupEnvironment, before it creates
# the SDL/UIKit window. Blocking there prevents SetupPresentation from ever
# running and leaves the iOS app as a black screen.
if "OnFinalizePaths(" not in method:
    raise SystemExit("missing asynchronous finalization hook")
header.write_text(text)
print("ASURA_IOS_FINALIZE_PATHS_LAUNCHER_V4_OK")
