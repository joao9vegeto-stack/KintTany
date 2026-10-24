#pragma once
// Xenos GLSL -> Vulkan SPIR-V compiler using Khronos glslang.
// A compiled shader is NOT a GPU draw; pipeline and EDRAM work remain separate.
#include <cstdint>
#include <string>
#include <vector>
namespace xowue::xenos {
struct SpirvCompilation {
    std::vector<uint32_t> words;
    std::string error;
};
SpirvCompilation CompileGlslToSpirv(uint32_t stage, const std::string &glsl);
}
