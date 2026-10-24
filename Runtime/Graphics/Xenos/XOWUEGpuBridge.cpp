// XOWUE graphics bridge. GPL-3.0-or-later.
// The translator is real Xenos microcode -> GLSL, but GLSL translation is
// NOT pipeline submission. This code does not claim draws reached the GPU.
#include "XOWUEGpuBridge.h"
#include "XOWUEGuestDraw.h"
#include <deque>
#include "shader_translator.h"
#include "XOWUESpirvCompiler.h"
#include <array>
#include <algorithm>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace xowue::xenos {
namespace {
struct ShaderRecord {
  bool valid = false;
  size_t glslBytes = 0;
  std::vector<uint32_t> spirv;
  std::string error;
  // Store generated GLSL for later Vulkan pipeline integration.
  std::string glsl;
  uint32_t vertexFetchMask = 0, interpolatorMask = 0, colorTargetMask = 0;
  uint32_t texture2DMask = 0, texture3DMask = 0, textureCubeMask = 0;
  bool usesMemExport = false;
  uint32_t fetchUsed[3]{}, fetchStrides[96]{}, fetchExtents[96]{};
};
std::mutex stateMutex;
std::array<uint32_t, 0x5003> registers{};
std::unordered_map<uint64_t, ShaderRecord> shaders;
std::unordered_map<std::string, std::vector<uint32_t>> linkedPixels;
uint64_t linkedPixelCompiled = 0, linkedPixelRejected = 0;
uint32_t linkedPixelLastInputs = 0;
uint64_t translated = 0, failed = 0, cacheHits = 0, observedDraws = 0;
uint64_t spirvCompiled = 0, spirvRejected = 0;
uint64_t vertexHash = 0, pixelHash = 0;
uint32_t lastDrawInitiator = 0;
std::deque<XOWUEGuestDraw> pendingDraws;
uint64_t submittedDraws = 0, rejectedDraws = 0, droppedDraws = 0;
std::string lastReject;

uint64_t Hash(uint32_t stage, const uint32_t* words, size_t count) {
  uint64_t hash = 14695981039346656037ull ^ stage;
  for (size_t i = 0; i < count; ++i)
    hash = (hash ^ words[i]) * 1099511628211ull;
  return hash ^ (count * 0x9E3779B97F4A7C15ull);
}
}

void Reset() {
  std::lock_guard lock(stateMutex);
  registers.fill(0);
  shaders.clear();
  linkedPixels.clear();
  linkedPixelCompiled = linkedPixelRejected = 0;
  linkedPixelLastInputs = 0;
  translated = failed = cacheHits = observedDraws = 0;
  spirvCompiled = spirvRejected = 0;
  vertexHash = pixelHash = 0;
  lastDrawInitiator = 0;
  pendingDraws.clear();
  submittedDraws = rejectedDraws = droppedDraws = 0;
  lastReject.clear();
}

void WriteRegister(uint32_t address, uint32_t value) {
  if (address >= registers.size()) return;
  std::lock_guard lock(stateMutex);
  registers[address] = value;
}

uint32_t ReadRegister(uint32_t address) {
  if (address >= registers.size()) return 0;
  std::lock_guard lock(stateMutex);
  return registers[address];
}

ShaderResult LoadShader(uint32_t stage, const uint32_t* words, size_t count) {
  ShaderResult result;
  if (stage > 1 || !words || !count || count > 65536) {
    result.error = "unsupported shader stage, address or length";
    std::lock_guard lock(stateMutex);
    ++failed;
    return result;
  }
  result.hash = Hash(stage, words, count);
  {
    std::lock_guard lock(stateMutex);
    if (const auto it = shaders.find(result.hash); it != shaders.end()) {
      result.valid = it->second.valid;
      result.glslBytes = it->second.glslBytes;
      result.spirvBytes = it->second.spirv.size() * 4u;
      result.spirvReady = !it->second.spirv.empty();
      result.error = it->second.error;
      result.fromCache = true;
      ++cacheHits;
      (stage == 0 ? vertexHash : pixelHash) = result.hash;
      return result;
    }
  }
  // The PM4 decoder already converts guest big-endian words into host
  // uint32_t. TranslateShader requires this host-order representation.
  gpu::TranslatedShader shader = gpu::TranslateShader(
      stage == 0 ? gpu::ShaderStage::Vertex : gpu::ShaderStage::Pixel,
      words, count);
  result.valid = shader.ok;
  result.glslBytes = shader.glsl.size();
  result.error = shader.error;
  SpirvCompilation compilation;
  // Real Xenos guest GLSL is compiled into SPIR-V only after translation.
  // The pipeline count stays zero until a renderer submits actual game draws.
  if (shader.ok) {
    compilation = CompileGlslToSpirv(stage, shader.glsl);
    result.spirvReady = !compilation.words.empty();
    result.spirvBytes = compilation.words.size() * 4u;
    if (!result.spirvReady && !compilation.error.empty())
      result.error = compilation.error;
  }
  {
    std::lock_guard lock(stateMutex);
    if (shader.ok) ++translated; else ++failed;
    if (shader.ok) {
      if (result.spirvReady) ++spirvCompiled;
      else ++spirvRejected;
    }
    (stage == 0 ? vertexHash : pixelHash) = result.hash;
    if (shaders.size() < 4096u) {
      ShaderRecord entry;
      entry.valid = shader.ok;
      entry.glslBytes = shader.glsl.size();
      entry.error = shader.error;
      entry.glsl = std::move(shader.glsl);
      entry.vertexFetchMask = shader.vertexFetchMask;
      entry.interpolatorMask = shader.interpolatorMask;
      entry.colorTargetMask = shader.colorTargetMask;
      entry.usesMemExport = shader.usesMemExport;
      entry.texture2DMask = shader.texture2DMask;
      entry.texture3DMask = shader.texture3DMask;
      entry.textureCubeMask = shader.textureCubeMask;
      for (uint32_t i = 0; i < 3u; ++i) entry.fetchUsed[i] = shader.vertexFetchConstants[i];
      for (uint32_t i = 0; i < 96u; ++i) {
        entry.fetchStrides[i] = shader.vertexStride[i];
        entry.fetchExtents[i] = shader.vertexExtent[i];
      }
      entry.spirv = std::move(compilation.words);
      shaders.emplace(result.hash, std::move(entry));
    } else if (shader.ok) {
      ++failed;
      result.valid = false;
      result.spirvReady = false;
      result.error = "XENOS_SHADER_CACHE_CAPACITY_4096_EXCEEDED";
    }
  }
  return result;
}

bool CopyShaderSpirv(uint64_t hash, std::vector<uint32_t>& words) {
  std::lock_guard lock(stateMutex);
  const auto it = shaders.find(hash);
  if (it == shaders.end() || it->second.spirv.empty()) return false;
  words = it->second.spirv;
  return true;
}

// Real guest fragment shader specialization: the Xenos translator deliberately
// hides pipeline-dependent varying inputs and render-target outputs behind
// preprocessor definitions. Without OUT0 the shader writes NO COLOR, even
// when Vulkan reports successful vkCmdDraw. Bind only VS-written interpolators.
extern "C" size_t xowue_xenos_linked_fragment_spirv_words(
    uint64_t vertex, uint64_t pixel, uint32_t* out, size_t capacity) {
  std::string key = std::to_string(vertex) + ":" + std::to_string(pixel);
  std::string source;
  uint32_t mask = 0;
  {
    std::lock_guard lock(stateMutex);
    if (auto c = linkedPixels.find(key); c != linkedPixels.end()) {
      if (!out) return c->second.size();
      if (capacity < c->second.size()) return 0;
      std::copy(c->second.begin(), c->second.end(), out);
      return c->second.size();
    }
    const auto v = shaders.find(vertex), p = shaders.find(pixel);
    if (v == shaders.end() || p == shaders.end() || v->second.glsl.empty() ||
        p->second.glsl.empty()) return 0;
    mask = v->second.interpolatorMask;
    source = p->second.glsl;
  }
  const std::string version = "#version 460";
  const size_t head = source.find(version);
  if (head != 0u) return 0; // never place defines before GLSL #version
  const size_t lineEnd = source.find('\n', head);
  if (lineEnd == std::string::npos) return 0;
  std::string defines = "\n#define OUT0 1\n";
  for (unsigned i = 0; i < 16u; ++i)
    if (mask & (1u << i))
      defines += "#define IN" + std::to_string(i) + " 1\n";
  source.insert(lineEnd + 1u, defines);
  SpirvCompilation compiled = CompileGlslToSpirv(1u, source);
  if (compiled.words.empty()) {
    std::lock_guard lock(stateMutex);
    ++linkedPixelRejected;
    lastReject = "XENOS_GUEST_FRAGMENT_LINK_FAILED: " + compiled.error;
    return 0;
  }
  std::lock_guard lock(stateMutex);
  if (linkedPixels.size() >= 128u) linkedPixels.clear();
  auto [slot, created] = linkedPixels.try_emplace(key, std::move(compiled.words));
  if (created) ++linkedPixelCompiled;
  linkedPixelLastInputs = mask;
  if (!out) return slot->second.size();
  if (capacity < slot->second.size()) return 0;
  std::copy(slot->second.begin(), slot->second.end(), out);
  return slot->second.size();
}

void ObserveDraw(uint32_t initiator) {
  std::lock_guard lock(stateMutex);
  ++observedDraws;
  lastDrawInitiator = initiator;
}


void QueueDraw(uint32_t initiator, uint32_t indexCount,
               uint32_t indexAddress, uint32_t indexInfo, uint32_t indexOffset) {
  std::lock_guard lock(stateMutex);
  ++observedDraws;
  lastDrawInitiator = initiator;
  const uint32_t edramMode=registers[0x2208u]&7u;
  const bool depthOnly=edramMode==5u;
  const bool copyMode=edramMode==6u;
  if (pendingDraws.size()>=XOWUE_GPU_MAX_DRAWS ||
      (!copyMode && (!indexCount || !vertexHash ||
                    (!depthOnly && !pixelHash)))) {
    ++droppedDraws;
    return;
  }
  const auto vs=shaders.find(vertexHash);
  const auto ps=shaders.find(pixelHash);
  const bool validVS=vs!=shaders.end() && !vs->second.spirv.empty();
  const bool validPS=ps!=shaders.end() && !ps->second.spirv.empty();
  if (!copyMode && (!validVS || (!depthOnly && !validPS))) {
    ++droppedDraws;
    return;
  }
  XOWUEGuestDraw packet{};
  packet.vertex_hash = copyMode?0u:vertexHash;
  packet.pixel_hash = (copyMode||depthOnly)?0u:pixelHash;
  packet.initiator = initiator;
  packet.index_count = indexCount;
  packet.index_address = indexAddress;
  packet.index_info = indexInfo;
  packet.index_offset = indexOffset;
  // Snapshot Xenos PA_CL_VTE_CNTL and guest viewport float bit patterns at
  // each PM4 draw. A zeroed constant is not equivalent to the GPU registers.
  // Addresses match Xenia's a2xx PA register definitions.
  packet.pa_cl_vte_cntl = registers[0x2206u];
  packet.rb_modecontrol = registers[0x2208u];
  packet.rb_surface_info = registers[0x2000u];
  packet.rb_depthcontrol = registers[0x2200u];
  packet.rb_color_mask = registers[0x2104u];
  packet.rb_color_info[0] = registers[0x2001u];
  packet.rb_color_info[1] = registers[0x2003u];
  packet.rb_color_info[2] = registers[0x2004u];
  packet.rb_color_info[3] = registers[0x2005u];
  packet.rb_depth_info = registers[0x2002u];
  packet.rb_copy_control = registers[0x2318u];
  packet.rb_copy_dest_base = registers[0x2319u];
  packet.rb_copy_dest_pitch = registers[0x231Au];
  packet.rb_copy_dest_info = registers[0x231Bu];
  packet.rb_blendcontrol[0] = registers[0x2201u];
  packet.rb_blendcontrol[1] = registers[0x2209u];
  packet.rb_blendcontrol[2] = registers[0x220Au];
  packet.rb_blendcontrol[3] = registers[0x220Bu];
  packet.pa_sc_window_scissor_tl = registers[0x2081u];
  packet.pa_sc_window_scissor_br = registers[0x2082u];
  packet.viewport_register_bits[0] = registers[0x210Fu]; // XSCALE
  packet.viewport_register_bits[1] = registers[0x2110u]; // XOFFSET
  packet.viewport_register_bits[2] = registers[0x2111u]; // YSCALE
  packet.viewport_register_bits[3] = registers[0x2112u]; // YOFFSET
  if(validVS && !copyMode) {
    packet.vertex_fetch_mask=vs->second.vertexFetchMask;
    packet.vertex_memexport=vs->second.usesMemExport?1u:0u;
    packet.texture_2d_mask=vs->second.texture2DMask;
    packet.texture_3d_mask=vs->second.texture3DMask;
    packet.texture_cube_mask=vs->second.textureCubeMask;
    for(uint32_t i=0;i<3u;++i)packet.fetch_used[i]=vs->second.fetchUsed[i];
    for(uint32_t i=0;i<96u;++i){
      packet.fetch_strides[i]=vs->second.fetchStrides[i];
      packet.fetch_extents[i]=vs->second.fetchExtents[i];
    }
  }
  if(validPS && !depthOnly && !copyMode) {
    packet.texture_2d_mask|=ps->second.texture2DMask;
    packet.texture_3d_mask|=ps->second.texture3DMask;
    packet.texture_cube_mask|=ps->second.textureCubeMask;
    packet.pixel_memexport=ps->second.usesMemExport?1u:0u;
    packet.color_target_mask=ps->second.colorTargetMask;
  }
  uint32_t pos = 0;
  for (uint32_t i = 0; i < 2048u; ++i) packet.constants[pos++] = registers[0x4000u + i];
  for (uint32_t i = 0; i < 192u; ++i) packet.constants[pos++] = registers[0x4800u + i];
  for (uint32_t i = 0; i < 8u; ++i) packet.constants[pos++] = registers[0x4900u + i];
  for (uint32_t i = 0; i < 32u; ++i) packet.constants[pos++] = registers[0x4908u + i];
  for (uint32_t i = 0; i < 16u; ++i) packet.constants[pos++] = 0;
  pendingDraws.push_back(packet);
}
extern "C" size_t xowue_xenos_take_draws(XOWUEGuestDraw *out, size_t capacity) {
  if (!out || capacity == 0) return 0;
  std::lock_guard lock(stateMutex);
  const size_t count = std::min(capacity, pendingDraws.size());
  for (size_t i = 0; i < count; ++i) {
    out[i] = std::move(pendingDraws.front());
    pendingDraws.pop_front();
  }
  return count;
}
extern "C" void xowue_xenos_record_submitted(uint32_t count) {
  std::lock_guard lock(stateMutex);
  submittedDraws += count;
}
extern "C" void xowue_xenos_record_rejected(uint32_t count, const char *why) {
  std::lock_guard lock(stateMutex);
  rejectedDraws += count;
  lastReject = why ? why : "unspecified";
}

// C ABI: the Objective-C Vulkan host consumes native guest shader binaries.
// Hashes refer to the exact Xenos microcode and are never placeholder shaders.
extern "C" bool xowue_xenos_active_shader_hashes(uint64_t *vertex, uint64_t *pixel) {
  if (!vertex || !pixel) return false;
  std::lock_guard lock(stateMutex);
  *vertex = vertexHash;
  *pixel = pixelHash;
  return *vertex != 0 && *pixel != 0;
}
extern "C" size_t xowue_xenos_spirv_words(uint64_t hash, uint32_t *out, size_t capacity) {
  std::lock_guard lock(stateMutex);
  const auto it = shaders.find(hash);
  if (it == shaders.end()) return 0;
  const auto &data = it->second.spirv;
  if (data.empty()) return 0;
  if (!out) return data.size();
  if (capacity < data.size()) return 0;
  std::copy(data.begin(), data.end(), out);
  return data.size();
}

std::string Diagnostics() {
  std::lock_guard lock(stateMutex);
  char value[480];
  std::snprintf(value, sizeof(value),
      "XENOS_SHADER_TRANSLATOR source=SpeedBreaker/Xenia "
      "translated=%" PRIu64 " rejected=%" PRIu64 " cache_hits=%" PRIu64
      " spirv_compiled=%" PRIu64 " spirv_rejected=%" PRIu64
      " observed_draws=%" PRIu64 " vertex_hash=%016" PRIX64
      " pixel_hash=%016" PRIX64 " initiator=%08X "
      "queued=%zu dropped=%" PRIu64 " pipeline_draws_submitted=%" PRIu64
      " pipeline_draws_rejected=%" PRIu64
      " linked_pixels=%" PRIu64 " linked_pixel_rejected=%" PRIu64
      " linked_varying_mask=%04X last_reject=%s",
      translated, failed, cacheHits, spirvCompiled, spirvRejected,
      observedDraws, vertexHash, pixelHash,
      lastDrawInitiator, pendingDraws.size(), droppedDraws, submittedDraws,
      rejectedDraws, linkedPixelCompiled, linkedPixelRejected,
      linkedPixelLastInputs, lastReject.c_str());
  return value;
}
}
