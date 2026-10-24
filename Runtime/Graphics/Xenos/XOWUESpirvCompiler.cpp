#include "XOWUESpirvCompiler.h"
#include <mutex>
#ifdef XOWUE_GLSLANG_ENABLED
#include <glslang/Include/glslang_c_interface.h>
#include <glslang/Public/resource_limits_c.h>
#endif
namespace xowue::xenos {
SpirvCompilation CompileGlslToSpirv(uint32_t stage, const std::string &glsl) {
    SpirvCompilation result;
    if (stage > 1u || glsl.empty()) {
        result.error = "invalid Xenos shader stage or empty GLSL";
        return result;
    }
#ifdef XOWUE_GLSLANG_ENABLED
    static std::once_flag initialize;
    static bool initialized = false;
    std::call_once(initialize, [] { initialized = glslang_initialize_process() != 0; });
    if (!initialized) {
        result.error = "glslang_initialize_process failed";
        return result;
    }
    const glslang_stage_t shaderStage = stage == 0u
        ? GLSLANG_STAGE_VERTEX : GLSLANG_STAGE_FRAGMENT;
    glslang_input_t input{};
    input.language = GLSLANG_SOURCE_GLSL;
    input.stage = shaderStage;
    input.client = GLSLANG_CLIENT_VULKAN;
    input.client_version = GLSLANG_TARGET_VULKAN_1_2;
    input.target_language = GLSLANG_TARGET_SPV;
    input.target_language_version = GLSLANG_TARGET_SPV_1_5;
    input.code = glsl.c_str();
    input.default_version = 460;
    input.default_profile = GLSLANG_NO_PROFILE;
    input.messages = glslang_messages_t(
        GLSLANG_MSG_SPV_RULES_BIT | GLSLANG_MSG_VULKAN_RULES_BIT);
    input.resource = glslang_default_resource();
    glslang_shader_t *shader = glslang_shader_create(&input);
    if (!shader) {
        result.error = "glslang_shader_create failed";
        return result;
    }
    if (!glslang_shader_preprocess(shader, &input) ||
        !glslang_shader_parse(shader, &input)) {
        const char *message = glslang_shader_get_info_log(shader);
        result.error = message ? message : "GLSL parsing failed";
        glslang_shader_delete(shader);
        return result;
    }
    glslang_program_t *program = glslang_program_create();
    if (!program) {
        glslang_shader_delete(shader);
        result.error = "glslang_program_create failed";
        return result;
    }
    glslang_program_add_shader(program, shader);
    if (!glslang_program_link(program,
        GLSLANG_MSG_SPV_RULES_BIT | GLSLANG_MSG_VULKAN_RULES_BIT)) {
        const char *message = glslang_program_get_info_log(program);
        result.error = message ? message : "SPIR-V link failed";
    } else {
        glslang_program_SPIRV_generate(program, shaderStage);
        const size_t size = glslang_program_SPIRV_get_size(program);
        if (size < 5 || size > (1u << 20u)) {
            result.error = "invalid SPIR-V word count";
        } else {
            result.words.resize(size);
            glslang_program_SPIRV_get(program, result.words.data());
            if (result.words[0] != 0x07230203u) {
                result.words.clear();
                result.error = "SPIR-V magic mismatch";
            }
        }
    }
    glslang_program_delete(program);
    glslang_shader_delete(shader);
#else
    result.error = "glslang not linked in this build";
#endif
    return result;
}
}
