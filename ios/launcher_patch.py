from pathlib import Path
root = Path(__file__).resolve().parents[1] / "upstream"
header = root / "src/asurawrath_app.h"
text = header.read_text()
marker = "// ASURA_IOS_NATIVE_LAUNCHER_V1"
if marker in text:
    raise SystemExit("launcher patch already applied")
text = text.replace('#include <rex/rex_app.h>', '#include <rex/rex_app.h>\n#include <imgui.h>\n#include <algorithm>\n#include <functional>\n#include <optional>\n#include <string>\n#include <vector>')
dialog = r"""
#ifndef ASURA_IOS_BUILD_NUMBER
#define ASURA_IOS_BUILD_NUMBER "1"
#endif
namespace {
std::filesystem::path ResolveAsuraGameRoot(const std::filesystem::path& candidate) {
  std::error_code ec;
  if (candidate.empty() || !std::filesystem::is_directory(candidate, ec)) return {};
  if (std::filesystem::is_regular_file(candidate / "default.xex", ec)) return candidate;
  if (std::filesystem::is_regular_file(candidate / "BCGame" / "default.xex", ec)) return candidate / "BCGame";
  if (std::filesystem::is_regular_file(candidate / "extracted" / "default.xex", ec)) return candidate / "extracted";
  if (std::filesystem::is_regular_file(candidate / "extracted" / "BCGame" / "default.xex", ec)) return candidate / "extracted" / "BCGame";
  return {};
}
std::filesystem::path FindAsuraGameRoot(const rex::PathConfig& paths) {
  const auto docs = paths.user_data_root;
  const auto bundle = rex::filesystem::GetExecutableFolder();
  const std::vector<std::filesystem::path> roots = {
    paths.game_data_root, docs, docs / "Asura's Wrath", docs / "AsurasWrath",
    docs / "Asura", docs / "Game", docs / "Games", docs / "game_data",
    bundle, bundle / "Asura's Wrath", bundle / "AsurasWrath",
    bundle.parent_path(), std::filesystem::current_path()
  };
  for (const auto& root : roots) {
    auto found = ResolveAsuraGameRoot(root);
    if (!found.empty()) return found;
  }
  std::error_code ec;
  if (!docs.empty() && std::filesystem::is_directory(docs, ec)) {
    for (std::filesystem::directory_iterator it(docs, ec), end; it != end && !ec; it.increment(ec)) {
      if (!it->is_directory(ec)) continue;
      auto found = ResolveAsuraGameRoot(it->path());
      if (!found.empty()) return found;
    }
  }
  return {};
}
class AsuraLauncherDialog final : public rex::ui::ImGuiDialog {
 public:
  AsuraLauncherDialog(rex::ui::ImGuiDrawer* drawer, rex::PathConfig defaults,
                      std::filesystem::path detected,
                      std::function<void(rex::PathConfig)> resume)
      : ImGuiDialog(drawer), paths_(std::move(defaults)),
        detected_(std::move(detected)), resume_(std::move(resume)) {}
 protected:
  void OnDraw(ImGuiIO& io) override {
    const float width = std::max(320.0f, std::min(820.0f, io.DisplaySize.x - 28.0f));
    const float height = std::max(260.0f, std::min(560.0f, io.DisplaySize.y - 24.0f));
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.5f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(ImVec2(width, height), ImGuiCond_Always);
    if (ImGui::Begin("ASURA'S WRATH  |  iOS", nullptr, ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings)) {
      ImGui::TextColored(ImVec4(0.95f, 0.16f, 0.12f, 1.0f), "ASURA'S WRATH");
      ImGui::SameLine();
      ImGui::TextDisabled("RECOMP  |  BUILD %s", ASURA_IOS_BUILD_NUMBER);
      ImGui::Separator();
      ImGui::TextWrapped("Recompilacao nativa ARM64 para iPhone. O jogo e procurado automaticamente na pasta Documents do aplicativo e na raiz do pacote.");
      ImGui::Spacing();
      if (!detected_.empty()) {
        ImGui::TextColored(ImVec4(0.25f, 0.88f, 0.48f, 1.0f), "JOGO DETECTADO");
        ImGui::TextWrapped("%s", detected_.string().c_str());
        const char* entries[] = {"default.xex", "AvatarAssetPack", "nxeart", "BCGame", "Xbox360TOC", "CookedXbox360", "Movies"};
        for (const char* entry : entries) {
          std::error_code ec;
          const bool exists = std::filesystem::exists(detected_ / entry, ec);
          ImGui::TextColored(exists ? ImVec4(0.25f, 0.88f, 0.48f, 1.0f) : ImVec4(0.92f, 0.62f, 0.20f, 1.0f), "%s  %s", exists ? "[OK]" : "[--]", entry);
        }
        ImGui::Spacing();
        if (ImGui::Button("INICIAR JOGO", ImVec2(-1.0f, 54.0f))) {
          rex::PathConfig selected = paths_;
          selected.game_data_root = detected_;
          auto resume = std::move(resume_);
          Close();
          if (resume) resume(std::move(selected));
        }
      } else {
        ImGui::TextColored(ImVec4(1.0f, 0.68f, 0.20f, 1.0f), "PASTA DO JOGO NAO ENCONTRADA");
        ImGui::TextWrapped("Copie a pasta completa do jogo para Documents do aplicativo (Arquivos > No meu iPhone > Asura's Wrath). O arquivo default.xex deve ficar na raiz da pasta do jogo.");
        ImGui::BulletText("default.xex");
        ImGui::BulletText("AvatarAssetPack/  |  nxeart/");
        ImGui::BulletText("BCGame/  |  CookedXbox360/");
        ImGui::BulletText("Xbox360TOC  |  Movies/");
        ImGui::Spacing();
        if (ImGui::Button("VERIFICAR NOVAMENTE", ImVec2(-1.0f, 50.0f))) detected_ = FindAsuraGameRoot(paths_);
      }
      ImGui::Separator();
      ImGui::TextDisabled("KosmicKrisp Vulkan  |  ReXGlue  |  KintTany");
      ImGui::TextDisabled("Build %s  -  iOS ARM64", ASURA_IOS_BUILD_NUMBER);
    }
    ImGui::End();
  }
 private:
  rex::PathConfig paths_;
  std::filesystem::path detected_;
  std::function<void(rex::PathConfig)> resume_;
};
}  // namespace
"""
text = text.replace("class AsurawrathApp : public rex::ReXApp {", dialog + "\n" + marker + "\nclass AsurawrathApp : public rex::ReXApp {")
method = r"""
  std::optional<rex::PathConfig> OnFinalizePaths(
      const rex::PathConfig& defaults,
      std::function<void(rex::PathConfig)> resume) override {
    auto detected = FindAsuraGameRoot(defaults);
    if (!detected.empty()) REXLOG_INFO("iOS launcher detected game data at {}", detected.string());
    else REXLOG_WARN("iOS launcher did not find default.xex in app Documents or bundle root");
    new AsuraLauncherDialog(imgui_drawer(), defaults, std::move(detected), std::move(resume));
    return std::nullopt;
  }
"""
assert text.count("\n};\n") == 1, "unexpected app class ending"
text = text.replace("\n};\n", "\n" + method + "\n};\n")
header.write_text(text)
print("ASURA_IOS_NATIVE_LAUNCHER_PATCH_OK")
