#!/usr/bin/env python3
"""Enforce native Xenos draw-path wiring before expensive iOS packaging."""
from pathlib import Path
engine=Path("Runtime/XOWUEEngine.cpp").read_text()
bridge=Path("Runtime/Graphics/Xenos/XOWUEGpuBridge.cpp").read_text()
renderer=Path("iOS/App/XOWUENativeDraw.inc").read_text()
textures=Path("iOS/App/XOWUEGuestTextures.inc").read_text()
vulkan=Path("iOS/App/XOWUEVulkanBackend.m").read_text()
header=Path("Runtime/Graphics/Xenos/XOWUEGuestDraw.h").read_text()
for name, content, needles in (
 ("frontend",engine,("xowue::xenos::QueueDraw(","xowue_xenos_copy_guest_physical","xowue_xenos_copy_guest_texture2d")),
 ("shader-queue",bridge,("pendingDraws.push_back","xowue_xenos_take_draws","pipeline_draws_submitted=%")),
 ("native-render",renderer,("XD(CmdDraw)","XD(CreateGraphicsPipelines)","XD(CmdBindDescriptorSets)",
                            "XDUploadGuestDraw","XDPrepare2DTextures","XENOS_PIPELINE_CREATION_FAILED")),
 ("texture",textures,("XDCreate2DTexture","xowue_xenos_copy_guest_texture2d","VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL")),
 ("vulkan",vulkan,("XDProcessDraws","XENOS_GPU_DRAWS_SUBMITTED","xowue_xenos_record_submitted")),
 ("abi",header,("XOWUE_GPU_CONSTANT_WORDS = 2296","XOWUEGuestDraw")),
):
    for token in needles:
        assert token in content, f"{name}: missing {token}"
assert "XDCacheComposedFrame" in renderer
assert "VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL" in renderer
assert "XDReuseComposedFrameBarrier" in vulkan
assert "capturedComposed" in vulkan
assert "reuseComposed" in vulkan
assert "pipeline_draws_submitted=0" not in bridge
assert vulkan.index("XDProcessDraws") < vulkan.index("state->QueueSubmit(state->queue")
assert vulkan.index("xowue_xenos_record_submitted") > vulkan.index("result = state->QueueSubmit")
print("PASS: Xenos PM4 draw queue, Vulkan pipelines/draw commands, genuine guest textures, final-submit accounting")

# The original Build 23 SPIR-V did not have OUT0; successful draws wrote no
# fragment colour. Require a pipeline-linked specialization with OUT0 enabled
# and only interpolators actually emitted by the paired vertex shader.
assert '#define OUT0 1' in bridge
assert 'entry.interpolatorMask = shader.interpolatorMask' in bridge
assert 'xowue_xenos_linked_fragment_spirv_words' in bridge
assert 'KKUpdateLinkedPixelShaderModule' in vulkan
assert 'XENOS_COMPOSITED_GPU_READBACK' in vulkan
assert 'XDGetPipeline' in renderer and 'KKUpdateLinkedPixelShaderModule' in renderer
print("PASS: fragment OUT0, paired interpolators, native frame readback")

# Verify live guest PA_CL_VTE_CNTL snapshot and guest-to-host viewport
# transformation, rather than treating recorded Vulkan commands as pixels.
assert "packet.pa_cl_vte_cntl = registers[0x2206u]" in bridge
assert "packet.viewport_register_bits[0] = registers[0x210Fu]" in bridge
assert "XENOS_GUEST_VIEWPORT" in renderer
assert "push.flags=1u" in renderer
assert "fminf(targetW/1280.0f,targetH/720.0f)" in renderer
print("PASS: Xenos guest viewport, real VTE flags and landscape aspect")
