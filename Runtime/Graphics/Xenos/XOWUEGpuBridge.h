// XOWUE bridge to the SpeedBreaker/Xenia Xenos shader translator.
// GPL-3.0-or-later; see ThirdPartyLicenses/SpeedBreaker-COPYING.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace xowue::xenos {
struct FrameLifecycleState { bool has_guest_swap=false, has_color_source=false, copied_to_swapchain=false, committed=false, stale=false, resolve_valid=false, nonblack_valid=false, black_screen_guard=false; uint32_t address=0,width=0,height=0,pitch=0,format=0,source_tile=0,copy_command=0,nonblack_pixels=0,resolve_status=0; uint64_t generation=0; };
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
void NotifyGuestSwap(uint32_t,uint32_t,uint32_t,uint32_t);
void NotifyGuestResolve(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
void NotifyGuestFrameCommitted();
void NotifyGuestFrameRejected(const char* reason); void NotifyGuestFramePixels(uint32_t width,uint32_t height,const uint8_t* pixels,size_t bytes); bool ShouldPresentGuestFrame(); bool HasFreshGuestFrame(); bool IsGuestFrameStale(); std::string FrameDiagnostics();
void QueueDraw(uint32_t initiator, uint32_t count, uint32_t address,
               uint32_t indexInfo, uint32_t indexOffset);
// Exact translated guest shaders, not proxy/fixed-function shaders.
// Return false until real Vulkan pipelines can consume them.
bool CopyShaderSpirv(uint64_t hash, std::vector<uint32_t>& words);
std::string Diagnostics();
}
