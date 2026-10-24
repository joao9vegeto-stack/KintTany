// XOWUE graphics bridge. GPL-3.0-or-later.
// The translator is real Xenos microcode -> GLSL, but GLSL translation is
// NOT pipeline submission. This code does not claim draws reached the GPU.
#include "XOWUEGpuBridge.h"
#include "shader_translator.h"
#include "XOWUESpirvCompiler.h"
#include <array>
#include <algorithm>
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
  std::vector<uint32_t> spirv;
  std::string error;
  // Store generated GLSL for later Vulkan pipeline integration.
  std::string glsl;
};
std::mutex stateMutex;
std::array<uint32_t, 0x5003> registers{};
std::unordered_map<uint64_t, ShaderRecord> shaders;
uint64_t translated = 0, failed = 0, cacheHits = 0, observedDraws = 0;
uint64_t spirvCompiled = 0, spirvRejected = 0;
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
  spirvCompiled = spirvRejected = 0;
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
    if (shaders.size() < 256) {
      ShaderRecord entry;
      entry.valid = shader.ok;
      entry.glslBytes = shader.glsl.size();
      entry.error = shader.error;
      entry.glsl = std::move(shader.glsl);
      entry.spirv = std::move(compilation.words);
      shaders.emplace(result.hash, std::move(entry));
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

void ObserveDraw(uint32_t initiator) {
  std::lock_guard lock(stateMutex);
  ++observedDraws;
  lastDrawInitiator = initiator;
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
      "pipeline_draws_submitted=0",
      translated, failed, cacheHits, spirvCompiled, spirvRejected,
      observedDraws, vertexHash, pixelHash,
      lastDrawInitiator);
  return value;
}
}
