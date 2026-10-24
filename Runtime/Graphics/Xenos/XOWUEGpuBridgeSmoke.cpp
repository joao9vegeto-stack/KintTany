// Native host smoke test for the linked Xenos shader translator.
// Does not claim rendered frames without Vulkan draws.
#include "XOWUEGpuBridge.h"
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
int main() {
  xowue::xenos::Reset();
  xowue::xenos::WriteRegister(0x4800u, 0x11223344u);
  xowue::xenos::ObserveDraw(0x21FCu);
  const uint32_t invalid[] = {0u};
  auto invalidStage = xowue::xenos::LoadShader(2u, invalid, 1u);
  assert(!invalidStage.valid);
  auto empty = xowue::xenos::LoadShader(0u, nullptr, 0u);
  assert(!empty.valid);
  std::string metrics = xowue::xenos::Diagnostics();
  assert(metrics.find("observed_draws=1") != std::string::npos);
  assert(metrics.find("pipeline_draws_submitted=0") != std::string::npos);
  xowue::xenos::Reset();
  assert(xowue::xenos::Diagnostics().find("observed_draws=0") != std::string::npos);
  std::cout << "PASS: Xenos shader bridge host smoke, no fabricated frames\n";
}
