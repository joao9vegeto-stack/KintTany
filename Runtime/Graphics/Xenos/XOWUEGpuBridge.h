// XOWUE bridge to the SpeedBreaker/Xenia Xenos shader translator.
// GPL-3.0-or-later; see ThirdPartyLicenses/SpeedBreaker-COPYING.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace xowue::xenos {
struct ShaderResult {
  bool valid = false;
  bool fromCache = false;
  uint64_t hash = 0;
  size_t glslBytes = 0;
  size_t spirvBytes = 0;
  bool spirvReady = false;
  std::string error;
};

void Reset();
void WriteRegister(uint32_t address, uint32_t value);
uint32_t ReadRegister(uint32_t address);
ShaderResult LoadShader(uint32_t stage, const uint32_t* hostOrderWords, size_t count);
void ObserveDraw(uint32_t initiator);
// Exact translated guest shaders, not proxy/fixed-function shaders.
// Return false until real Vulkan pipelines can consume them.
bool CopyShaderSpirv(uint64_t hash, std::vector<uint32_t>& words);
std::string Diagnostics();
}
