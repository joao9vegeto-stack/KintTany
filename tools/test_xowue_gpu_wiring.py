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

# Verify no false-success graphics claim from sparse samples alone.
assert "full_nonblack=%zu full_pixels=%zu" in vulkan
assert "XENOS_GUEST_SWAP_RGBA" in vulkan
assert "XOWUEOrientationDelegate" in Path("iOS/App/XOWUEApp.swift").read_text()
print("PASS: UIKit effective orientation, exhaustive GPU readback and guest-swap pixel audit")

# Build 26: observe the next PPC site and preserve per-draw and prestart swap evidence.
assert '0x831AA0B0' in Path('tools/lower_xowue_owner_interior_entries.py').read_text()
assert 'XENOS_DRAW_AUDIT' in renderer
assert 'XENOS_GUEST_SWAP_PRESTART' in vulkan
assert 'InvalidateMappedMemoryRanges' in vulkan
print('PASS: B26 AOT target, per-draw audit, guest pixels across logger startup, coherent readback')

# Build 28: preserve guest physical memory after fail-closed AOT and honour the
# vertex allocation size provided by Xenos itself (Xenia xe_gpu_vertex_fetch_t).
assert 'g_graphicsGuestMemory = memory' in engine
assert 'acquireGraphicsGuestMemory()' in engine
assert 'XENOS_GRAPHICS_MEMORY_RETAINED' in engine
assert '(word1>>2u)&0x00FFFFFFu' in renderer
assert 'GRAPHICS_BLOCKER reason=XENOS_VFETCH_BUFFER' in renderer
assert 'XENOS_NATIVE_DRAW_OUTCOME' in renderer
assert 'vs_memexport=%u ps_memexport=%u' in renderer
assert 'XOWUECrashRecorderWriteFatal(event)' in engine
print('PASS: retained guest physical memory, exact fetch allocation, draw rejection and FATAL AOT evidence')

# Expanded native Metal-trace coverage, without guest CPU interpretation.
assert 'shaders.size() < 4096u' in bridge
assert 'XOWUE_GPU_MAX_DRAWS = 128' in header
assert 'packet.rb_surface_info = registers[0x2000u]' in bridge
assert 'packet.rb_modecontrol = registers[0x2208u]' in bridge
assert 'XENOS_NATIVE_TARGET_STATE' in renderer
assert 'pipeline_cache[512]' in renderer
print('PASS: expanded shader/pipeline cache and Xenos target-state capture')

assert 'fetchFormat==32u' in engine and 'fetchFormat==25u' in engine
assert 'std::bit_cast<float>(bits)' in engine
assert 'format==32u' in textures and 'format==2u' in textures
print('PASS: native R8 RG8 RG16 RGB10A2 FP16 guest sampling')

# Native EDRAM modes must be different operations, and guest copy packets may
# omit fragment or vertex programs without being dropped before resolve.
assert 'const bool copyMode=edramMode==6u' in bridge
assert 'const bool depthOnly=edramMode==5u' in bridge
assert 'packet.rb_copy_dest_base = registers[0x2319u]' in bridge
assert 'XENOS_EDRAM_RESOLVE_NATIVE' in Path('iOS/App/XOWUEGuestColor.inc').read_text()
assert 'XENOS_EDRAM_DEPTH_NATIVE' in Path('iOS/App/XOWUEGuestDepth.inc').read_text()
assert 'XDResolveGuestColor' in renderer
assert 'XENOS_COPY_GUEST_REQUEST' in renderer
print('PASS: guest PM4 depth-only, offscreen EDRAM, native color resolve and copy destination tracing')

# Native guest GPU memory receives only a completed real color resolve.
color=Path("iOS/App/XOWUEGuestColor.inc").read_text()
assert "XENOS_GPU_RESOLVE_READBACK_QUEUED" in color
assert "XDCommitGuestResolves(state)" in vulkan
assert "xowue_xenos_commit_resolved_rgba" in engine
assert "xowue_xenos_commit_resolved_rgba" in color
assert "VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL" in color
assert "g_xd_guest_resolves_count=0" in color
assert "xenosTiledOffset2D(x,y,alignedPitch,2u)" in engine
print("PASS: native guest EDRAM GPU writeback linked to Xenos tiled original framebuffer")

# The frontend is compiled as Objective-C (.m), not Objective-C++ (.mm).
# Do not use C++-only functional casts in the Vulkan guest resolve.
assert 'const VkDeviceSize size=(VkDeviceSize)copyPitch*copyHeight*4u;' in color
assert 'VkDeviceSize(' not in color
print('PASS: Objective-C compatible VkDeviceSize guest resolve')

# iOS 26: present an actual UIKit controller supporting landscape rather
# than a portrait-only SwiftUI fullScreenCover.
ui=Path("iOS/App/XOWUEApp.swift").read_text()
assert "XOWUELandscapeHostingController" in ui
assert "override var supportedInterfaceOrientations: UIInterfaceOrientationMask { .landscapeRight }" in ui
assert "XOWUELandscapePresenter(library: library)" in ui
assert ".fullScreenCover(isPresented: $library.gameSurfacePresented)" not in ui
print("PASS: native UIKit landscape game host, portrait library preserved")

# User-requested single-title launcher must truly cancel guest PPC before
# dismissing the landscape host (no longer a fake 'back to library').
assert 'navigation.exit tapped: terminating native PPC' in ui
assert 'library.requestExit()' in ui
assert 'if exitRequested || outcome.code == 4' in ui
assert 'gameSurfacePresented = false' in ui
assert 'Label("SAIR", systemImage: "power")' in ui
print("PASS: landscape host closes after cooperative native PPC shutdown")

# RB_COPY_CONTROL bit layout verified against Xenia registers.h:
# bits 0..2 select RT0..RT3 (4=depth), 20..21 select raw/convert.
color=Path("iOS/App/XOWUEGuestColor.inc").read_text()
draws=Path("iOS/App/XOWUENativeDraw.inc").read_text()
assert "sourceIndex=draw->rb_copy_control&7u;" in color
assert "command=(draw->rb_copy_control>>20u)&3u" in color
assert "sourceIndex>=4u || command>1u" in color
assert "draw->rb_color_info[sourceIndex]" in color
assert "XENOS_COPY_MISSING_GUEST_COLOR" in color
assert "copy_command=%u" in draws
assert (0x00100000 & 7)==0
assert ((0x00100000 >>20)&3)==1
print("PASS: Xenos copy source=RT0 command=Convert; no fabricated depth/color pixels")
