// XOWUE graphics bridge. GPL-3.0-or-later.
// The translator is real Xenos microcode -> GLSL, but GLSL translation is
// NOT pipeline submission. This code does not claim draws reached the GPU.
#include "XOWUEGpuBridge.h"
#include "shader_translator.h"
#include <array>
#include <cinttypes>
#include <cstdio>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace xowue::xenos {
namespace {
struct ShaderRecord {
  bool valid = false;
  size_t glslBytes = 0;
  std::string error;
  // Store generated GLSL for later Vulkan pipeline integration.
  std::string glsl;
};
std::mutex stateMutex;
std::array<uint32_t, 0x5003> registers{};
std::unordered_map<uint64_t, ShaderRecord> shaders;
uint64_t translated = 0, failed = 0, cacheHits = 0, observedDraws = 0;
uint64_t vertexHash = 0, pixelHash = 0;
uint32_t lastDrawInitiator = 0;

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
  translated = failed = cacheHits = observedDraws = 0;
  vertexHash = pixelHash = 0;
  lastDrawInitiator = 0;
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
  {
    std::lock_guard lock(stateMutex);
    if (shader.ok) ++translated; else ++failed;
    (stage == 0 ? vertexHash : pixelHash) = result.hash;
    if (shaders.size() < 256) {
      ShaderRecord entry;
      entry.valid = shader.ok;
      entry.glslBytes = shader.glsl.size();
      entry.error = shader.error;
      entry.glsl = std::move(shader.glsl);
      shaders.emplace(result.hash, std::move(entry));
    }
  }
  return result;
}

void ObserveDraw(uint32_t initiator) {
  std::lock_guard lock(stateMutex);
  ++observedDraws;
  lastDrawInitiator = initiator;
}

std::string Diagnostics() {
  std::lock_guard lock(stateMutex);
  char value[420];
  std::snprintf(value, sizeof(value),
      "XENOS_SHADER_TRANSLATOR source=SpeedBreaker/Xenia "
      "translated=%" PRIu64 " rejected=%" PRIu64 " cache_hits=%" PRIu64
      " observed_draws=%" PRIu64 " vertex_hash=%016" PRIX64
      " pixel_hash=%016" PRIX64 " initiator=%08X "
      "pipeline_draws_submitted=0",
      translated, failed, cacheHits, observedDraws, vertexHash, pixelHash,
      lastDrawInitiator);
  return value;
}
}
