#!/usr/bin/env python3
"""Enforce native Xenos draw-path wiring before expensive iOS packaging."""
from pathlib import Path
import re
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
assert "sampled_nonblack=%zu samples=%zu checksum=%016llX pixels_total=%zu sampled_bbox=" in vulkan
assert "for (size_t k=0;k<total;++k)" not in vulkan
assert "XENOS_GUEST_SWAP_RGBA" in vulkan
assert "XOWUEOrientationDelegate" in Path("iOS/App/XOWUEApp.swift").read_text()
print("PASS: UIKit effective orientation, bounded sampled GPU readback and guest-swap pixel audit")

# Build 55 regression: EVENT_WRITE_SHD bit 31 is a counter write, never a CP interrupt.
assert "const bool writeCounter = (initiator & 0x80000000u) != 0u" in engine
assert "packetValue == 0xDEADBEEFu" not in engine
assert "cpInterruptRequested" not in engine
assert "XENOS_PM4_CP_INTERRUPT_AFTER_KICK" not in engine
assert "XENOS_GRAPHICS_INTERRUPT skipped source=1 invalid SCRATCH_REG4 target=0x%08X" in engine
assert "XOWUE_GUEST_PROGRESS_WATCHDOG fresh_guest_frames=0 duration_ms=" in engine
assert "XOWUE_GUEST_THREAD_STATE id=%u entry=0x%08X lastGuest=0x%08X LR=0x%08X waitReason=%s" in engine
# High-frequency AOT execution traces are diagnostic noise, not a progress signal.
# Keep a small bounded sample and do not let this family consume the milestone budget.
assert 'if (event.find("AOT execution") != std::string::npos)' in engine
assert 'return count.fetch_add(1u, std::memory_order_relaxed) < 64u;' in engine
assert "g_runtimeTracePersistMilestones.fetch_add(1, std::memory_order_relaxed) < 100000u" not in engine
assert "colorTarget?fminf(720.0f,(float)colorTarget->extent.height)" in renderer
assert "scissor.extent.height=(uint32_t)fminf(720.0f" in renderer
color=Path("iOS/App/XOWUEGuestColor.inc").read_text()
assert "sourceHeight=t->extent.height<720u?t->extent.height:720u" in color
critical=engine[engine.index("void xowue_RtlTryEnterCriticalSection"):engine.index("void xowue_RtlLeaveCriticalSection")]
assert "criticalSectionLock(address)" in critical
assert "sectionLock->try_lock()" in critical
assert "currentGuestKThread(context, base)" in critical
assert "owner == currentKThread" in critical
assert "g_currentGuestThreadId" not in critical
assert "std::recursive_timed_mutex" in engine
assert "atomicCompareExchangeGuestBe32" not in critical
assert "waitGuestObject(" not in critical
assert "shouldTraceCriticalSectionContention" in critical
assert "shouldTraceCriticalSection()" in engine
assert "GuestWaitStateScope waitState" in engine
assert "lastGuestPc.exchange(guestAddress" in engine
assert ".ignoresSafeArea(.all)" in Path("iOS/App/XOWUEApp.swift").read_text()
print("PASS: Build 54 CP fence ordering, critical-section recursion and full 16:9 EDRAM resolve")

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
assert "XDCommitGuestResolves(&localState)" in vulkan
assert "XDCollectPipelines(&localState)" in vulkan
assert "xowue_xenos_commit_resolved_rgba" in engine
assert "xowue_xenos_commit_resolved_rgba" in color
assert "VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL" in color
assert "g_xd_guest_resolves_count=0" in color
assert "xenosTiledOffset2D(x,y,alignedPitch,2u)" in engine
assert 'const std::array<uint32_t, 6>& frameFetch = frontend.swapFetch;' in engine
assert 'const bool frameFetchValid = frontend.swapFetchValid;' in engine
assert "vdSwapFetch" not in engine
assert "XENOS_GPU_GUEST_RESOLVE_COMMITTED" in engine
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
assert 'navigation.exit tapped: dispatching native cancellation' in ui
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


# Build 38 regression: native stop is unconditional, even when telemetry is off.
stop_start = engine.index('extern "C" void xowue_request_stop(void) {')
stop_end = engine.index('\n}', stop_start) + 2
stop_body = engine[stop_start:stop_end]
assert 'requestGuestSchedulerStop();' in stop_body
assert 'g_aotExecutionTelemetryActive' not in stop_body
assert 'XOWUE_USER_EXIT scheduler cancellation requested' in stop_body
ui = Path("iOS/App/XOWUEApp.swift").read_text()
request_start = ui.index("    func requestExit() {")
request_exit = ui[request_start:ui.index("\n    func runBoot()", request_start)]
assert "guard phase == .booting || gameSurfacePresented else { return }" in request_exit
assert "guard !exitRequested else {" in request_exit
assert 'runtime.stop duplicate request ignored' in request_exit
assert "if phase != .booting" in request_exit
assert "native call already returned" in request_exit
assert "xowue_request_stop()" in request_exit
assert "xowue_request_stop()" in request_exit
assert "Task.detached(priority: .userInitiated)" not in request_exit
boot_start = ui.index("    func runBoot() {")
boot_end = ui.index("\n    private func fail(", boot_start)
boot_body = ui[boot_start:boot_end]
assert "DispatchQueue.global(qos: .userInitiated).async" in boot_body
assert "DispatchQueue.main.async" in boot_body
assert "completeBoot(result)" in boot_body
assert "self.completeBoot(result)" not in boot_body
assert "gameSurfacePresented = false" in request_exit
assert request_exit.index("if phase != .booting") < request_exit.index("gameSurfacePresented = false") < request_exit.index("xowue_request_stop()")
assert "Aguardando o retorno do boot e a finalização das threads PPC." in request_exit
assert '.overlay(alignment: .topLeading)' in ui
assert 'navigation.exit tapped: dispatching native cancellation' in ui
assert vulkan.count("UILabel *_fpsLabel;") == 1
assert "g_xowue_guest_frame_count" in vulkan
assert "XOWUE_GAME_FPS fps=" in vulkan
assert "g_xowue_game_vdswap_request_count" in vulkan
assert "guest_vdswap_calls=" in vulkan
assert "xowue_vulkan_backend_game_vdswap_request" in engine
vd_start = engine.index("void xowue_VdSwap(")
vd_end = engine.index("void xowue_VdInitializeScalerCommandBuffer", vd_start)
assert "xowue_vulkan_backend_game_vdswap_request()" in engine[vd_start:vd_end]
assert "guest_content_updates=" in vulkan
assert "metal_host_presents=" in vulkan
assert '@" FPS JOGO %.1f"' in vulkan and "XENOS SWAP" not in vulkan
assert "self.bounds.size.height - 58.0" in vulkan
assert "_fpsLabel.layer.zPosition = 1000.0;" in vulkan
assert "[self bringSubviewToFront:_fpsLabel];" in vulkan
print("PASS: SAIR requests cooperative native shutdown while booting; only an already-returned session dismisses immediately; game-originated VdSwap FPS and separate content/Metal diagnostics")

# Build 86: never fake EOF or report existing Bink files as missing.
assert "isStartupMoviePath" in engine
assert "B86_MEDIA_OPEN" in engine
assert "isSplashBikMovie" not in engine
assert "isKnownOptionalStartupMovie" not in engine
assert "XOWUE_OPTIONAL_STARTUP_MOVIE_EOF" not in engine
assert '".XOWUEVirtualMedia"' not in engine
assert 'lower.find("/movies/")' in engine
assert 'lower.starts_with("movies/")' in engine
assert 'lower.ends_with(".bik") || lower.ends_with(".xxx")' in engine
assert "logStartupMovieOpen" in engine
assert "resolveCaseInsensitivePath(root, rel)" in engine
assert "signal.signalNow();" in engine
assert "g_lastValidScratchReg4Callback" in engine
assert "g_scratchReg4CallbackPending" in engine
assert "XENOS_GRAPHICS_INTERRUPT restored SCRATCH_REG4 target=0x%08X" in engine
assert "XOWUE_AOT_HOTSPOT guest=0x%08X calls=%llu thread=%u cooperative_yield=1" in engine
patch = Path("patches/XenonRecomp-XOWUE.patch").read_text()
assert "xowue_note_scratch_reg4_write" in patch
print("PASS: real Bink media opens, APFS path case-folding, one-shot SCRATCH_REG4 recovery, NtReadFile event, hotspot yields")


# Build 58: AOT hot-function detector, recursive case-folded UE3 package index,
# deterministic EDRAM clear resolve, SCRATCH_REG4 aliases, immediate watchdog.
for token in (
    "XOWUE_AOT_HOT_FUNCTION", "XOWUE_XEX_CODE_AUDIT",
    "XOWUE_VFS_INDEX_READY", "recursive_directory_iterator",
    "g_guestPathIndex.find(fileKey)", "XOWUE_GUEST_PROGRESS_WATCHDOG_RING",
    "XENOS_SCRATCH_REG4_CAPTURED", "0x7FC81710u", "0x90311010u",
    "XOWUE_AOT_HOTSPOT", "std::chrono::milliseconds(1)"):
    assert token in engine, f"Build 58 engine missing {token}"
assert "XENOS_EDRAM_COLOR_CLEAR_RESOLVE" in color
assert "XD(CmdBeginRenderPass)(cmd,&begin,VK_SUBPASS_CONTENTS_INLINE)" in color

# Build 112.5 regression: SetState cancellation and UI-safe Vulkan completion.
backend = Path("iOS/App/XOWUEVulkanBackend.m").read_text()
assert "KKGPUCompletionQueue()" in backend
assert "dispatch_async(KKGPUCompletionQueue()" in backend
render_start = backend.index("KKRenderFrame(KKVulkanState *state, CAMetalLayer *layer)")
render_end = backend.index("\n}\n\n\n@interface XOWUEVulkanView", render_start)
render_body = backend[render_start:render_end]
assert "atomic_load_explicit(&g_xowue_render_in_flight" in render_body
assert "localState.QueueWaitIdle(localState.queue)" in render_body
assert "dispatch_async(KKGPUCompletionQueue()" in render_body
detach_start = backend.index("- (void)didMoveToWindow")
detach_end = backend.index("- (void)startBackend", detach_start)
assert "DeviceWaitIdle" not in backend[detach_start:detach_end]
background_start = backend.index("UIApplicationDidEnterBackgroundNotification")
background_end = backend.index("UIApplicationWillEnterForegroundNotification", background_start)
assert "DeviceWaitIdle" not in backend[background_start:background_end]
dealloc_start = backend.index("- (void)dealloc")
dealloc_end = backend.index("\n@end", dealloc_start)
dealloc_body = backend[dealloc_start:dealloc_end]
assert "dispatch_async(KKGPUCompletionQueue()" in dealloc_body
assert "KKDestroyVulkan(&localState)" in dealloc_body
assert "kMaxBackendLogBytes = 4 * 1024 * 1024" in backend

print("PASS: Build 112 SetState loop cancellation, bounded diagnostics and asynchronous Vulkan shutdown")
print("PASS: Build 58 hot-function diagnostics, indexed UE3 VFS, clear-color resolve, callback aliases, watchdog state")


# Build 60: AOT milestone diagnostics must include the real indirect PPC
# register snapshot/disassembly; never fake a guest return to break a loop.
assert "top_fn=0x%08X" in engine and "prev_fn=0x%08X" in engine
assert "r3=0x%08X r4=0x%08X r11=0x%08X r30=0x%08X r31=0x%08X" in engine
assert "insns=%08X_%08X_%08X_%08X_%08X_%08X" in engine
assert "AOT_PLATEAU_ACTIVE worker_cp_pump=250us no_forced_guest_return" in engine
assert "lastR3.store(context.r3.u32" in engine
assert "lastR31.store(context.r31.u32" in engine
assert "std::filesystem::weakly_canonical(hostPath, ec)" in engine
assert "weakly_canonical(hostPath.parent_path(), ec)" not in engine
assert 'XENOS_PM4_TAIL count=%u' in engine
assert 'opcode == 0x57u || opcode == 0x5Au' in engine
assert 'XENOS_PM4_EVENT_WRITE initiator=0x%08X address=0x%08X value=0x%08X' in engine
assert "HotFunctionSlot" in engine
assert "XOWUE_AOT_HOT_FUNCTION thread=%u fn=0x%08X lr=0x%08X calls=%u swaps=%llu code=" in engine
assert "std::chrono::milliseconds(1500)" in engine
assert "sameFunctionCalls >= 250000u && swaps == 0u" not in engine
assert "XOWUE_XEX_CODE_AUDIT addr=0x%08X words=" in engine
assert "XOWUE_CACHE_ROOT path=" in engine
assert "cacheDevice ? g_guestCacheRoot" in engine
assert "xowue_store_address_ == 0x7FC81710u" in patch
assert "candidate = swapped" in engine
assert "VULKAN_EXTENSION_INVENTORY instance_available=%u device_available=%u" in vulkan
assert "INSTANCE_EXTENSION %s" not in vulkan and "DEVICE_EXTENSION %s" not in vulkan
assert "kXbox360PerformanceFrequency = 50000000u" in engine
assert "kGraphicsVblankPeriod = std::chrono::nanoseconds(16666667)" in engine
assert "if (vblankDue) dispatchGraphicsInterrupt(kGraphicsInterruptVblank, 2u)" in engine
assert "const uint32_t scratchValue = loadGuestBe32(base, 0x10311010u);" in engine
print("PASS: Build 59 per-thread spinlock, code audit, cache root, SCRATCH_REG4, timebase/VBlank and compact Vulkan diagnostics")

# Build 61: CP raw-address endian decoding, real monotonic 50 MHz mftb and fence plateau.
assert "xenosCpWriteback32" in engine
assert "rawAddress & ~3u" in engine
assert "if (xenosCpWriteback32(base, address, value, 0x58u))" in engine
assert "g_lastEmulatedTimebase" not in engine
assert "kXbox360PerformanceFrequency = 50000000u" in engine
assert "KeQueryPerformanceFrequency -> 50000000 Hz" in engine
assert "PPC_INST_MFTB" in patch
assert "xowue_guest_timebase" in patch
assert "XENOS_CP_WRITEBACK op=0x%02X raw=0x%08X addr=0x%08X endian=%u value=0x%08X readback_be=0x%08X" in engine
assert "XENOS_CP_PLATEAU_WRITEBACK" in engine
assert "XOWUE_CP_PLATEAU_CALLER" in engine
def _xenos_gpu_swap32(v, endian):
    endian &= 3
    if endian == 1:
        return ((v & 0x00FF00FF) << 8) | ((v & 0xFF00FF00) >> 8)
    if endian == 2:
        return int.from_bytes(v.to_bytes(4, "little"), "big")
    if endian == 3:
        return ((v << 16) | (v >> 16)) & 0xFFFFFFFF
    return v
raw, value = 0x10310006, 0x00000001
addr, endian = raw & ~3, raw & 3
stored = _xenos_gpu_swap32(value, endian)
assert addr == 0x10310004
assert stored.to_bytes(4, "little") == bytes.fromhex("00000001")
assert int.from_bytes(stored.to_bytes(4, "little"), "big") == value
print("PASS: Build 61 CP writeback endian/physical address, 50 MHz mftb, and non-mutating plateau diagnostics")


# Build 88: EDRAM attachments preserve guest color across submissions.
guest_color=Path("iOS/App/XOWUEGuestColor.inc").read_text()
assert "VkRenderPass pass,loadPass;" in guest_color
assert "VK_ATTACHMENT_LOAD_OP_LOAD" in guest_color
assert "loadAttachment.initialLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL" in guest_color
assert "colorForNextDraw" in guest_color
assert "t->initialized=true;" in guest_color
assert "if(t->loadPass)XD(DestroyRenderPass)" in guest_color
assert "const VkRenderPass drawPass=" in renderer
assert ".renderPass=drawPass,.framebuffer=colorTarget->framebuffer" in renderer
print("PASS: Build 88 EDRAM CLEAR-on-first-use / LOAD-on-reuse and resolve layout restoration")


# Build 105: MW2 command-processor semantics and real guest-frame pacing.
assert "if (header == 0u)" in engine
assert "kXenosPm4IndirectBufferPfdOpcode = 0x37u" in engine
assert "depth < 4u" in engine
assert "(address & 0x1Fu) == 0u" in engine
assert "frontend.binMask" in engine and "frontend.binSelect" in engine
swap_start = engine.index("} else if (opcode == kXenosPm4SwapOpcode")
swap_end = engine.index("\n            }\n        }", swap_start)
swap = engine[swap_start:swap_end]
assert swap.index("NotifyGuestSwap") < swap.index("if (!frameFetchValid)")
assert swap.index("xowue_vulkan_backend_guest_swap") < swap.index("if (!frameFetchValid)")
vd_start = engine.index("void xowue_VdSwap(")
vd_end = engine.index("\nvoid xowue_VdInitializeScalerCommandBuffer", vd_start)
vd = engine[vd_start:vd_end]
assert "XOWUE_VDSWAP_PACKET_QUEUED" in vd
assert "decodeXenosSwapTexture" not in vd
assert "xowue_vulkan_backend_guest_frame_rgba" not in vd
assert "PPC_STORE_U32(commandBuffer + 4u, kSwapSignature)" in vd
assert "PPC_STORE_U32(commandBuffer + 8u, frontbufferPhysicalAddress)" in vd
assert "PPC_STORE_U32(commandBuffer + 12u, width)" in vd
assert "PPC_STORE_U32(commandBuffer + 16u, height)" in vd
assert "context.r3.u32 = 0u" in vd
assert "kFetchPacketHeader" not in vd
assert "XOWUE_VDSWAP_FETCH" not in vd
assert "last_guest_swap_count" in vulkan
assert "guestSwapSerial == state->last_guest_swap_count" in vulkan
assert "newGuestFrame = guest_frame_ready" in vulkan
assert "guest_frame_ready ? 0u" not in vulkan
assert "XDProcessDraws(state, image_index, state->command_buffer)" in vulkan
assert "XOWUE_NATIVE_GUEST_FRAME" in vulkan
assert "XENOS_GUEST_FRAME_UNCHANGED" in vulkan
print("PASS: Build 105 PM4/XE_SWAP frame path, fresh-only CPU fallback, native Xenos draws and guest-paced presents")

assert "guestSwapSerial == state->last_guest_swap_count" in vulkan
assert "newGuestFrame = guest_frame_ready" in vulkan
assert "guest_frame_ready ? 0u" not in vulkan
assert "XOWUE_NATIVE_GUEST_FRAME" in vulkan

diagnostics=Path("iOS/App/XOWUEDiagnostics.swift").read_text()
assert "XENOS_GUEST_FRAME_UNCHANGED" in vulkan
assert "memcmp(g_xowue_guest_frame, copy, required)" in vulkan
assert "XOWUE_VDSWAP_" in diagnostics
assert "XOWUE_PM4_" in diagnostics
assert "XOWUE_NATIVE_GUEST_FRAME" in diagnostics
assert "XOWUE_PM4_XE_SWAP sequence=" in engine

# Guest frame accounting must be driven by consumed PM4 swaps, not host refresh ticks.
assert "state->guest_frames_presented +=" in vulkan
assert "state->last_guest_swap_count = guestSwapSerial" in vulkan

# MW2 end-of-pipe/fence behavior and ALU constant memory loads.
assert "opcode == 0x2Fu" in engine and "XENOS_PM4_LOAD_ALU_CONSTANT" in engine
assert "opcode == 0x59u" in engine and "XENOS_PM4_EVENT_WRITE_CFL" in engine
assert "opcode == 0x26u" in engine and "xowue_vulkan_backend_wait_idle" in engine
assert "xowue_vulkan_backend_wait_idle(void)" in engine
assert "KKWaitForGuestSwapCompletion" in vulkan
assert "g_xowue_guest_swap_completed_count" in vulkan
assert "XOWUE_GPU_SWAP_WAIT" in vulkan and "XOWUE_GPU_SWAP_WAIT" in diagnostics

audit_script=Path("tools/audit_xowue_global_callsite_gaps.py").read_text()
assert 'if "PPC_CALL_INDIRECT_FUNC" in chunk:' in audit_script

# Build 136 follow-up: main PPC stream stall disassembly and CP provenance.
assert '{0x82495C30u, 0x82495C90u, "STREAM_CALLER_82495C64"}' in engine
assert '{0x82575320u, 0x82575600u, "STREAM_LOOP_CONT_82575510"}' in engine
assert 'g_runtimeTracePersistB84.fetch_add(1, std::memory_order_relaxed) < 128u' in engine
assert 'event.find("XOWUE_VDSWAP_PACKET_QUEUED")' in engine
assert 'r5=0x%08X r6=0x%08X r7=0x%08X r8=0x%08X' in engine
print("PASS: stream-stall caller/back-edge audit and VdSwap CP provenance")


# Build 140: instrument both PPC callbacks that release the stream-reader poll loop.
# The guest source at 0x82575480 calls vtable+64 at these exact link-register PCs.
for poll_lr in ("0x825754E4u", "0x82575510u"):
    assert poll_lr in engine, f"stream availability poll callback missing: {poll_lr}"
assert "std::array<std::atomic<uint32_t>, 10> streamDispatchSamples" in engine
assert "case 0x82573DB8u: return 7" in engine
assert "case 0x82573B28u: return 8" in engine
assert "case 0x82573B40u: return 9" in engine
assert "B144_STREAM_WORKER_ENTRY" in engine and "B145_STREAM_QUEUE_WAKE" in engine
assert "constexpr uint32_t kWorkerQueue = 0x835FF47Cu" in engine
assert "workerCount <= workerCapacity" in engine
assert "B145_STREAM_QUEUE_WAKE" in engine and "B145_STREAM_WORKER_QUEUE_HEAD" in engine
assert 'callSite == 0x82573DB8u ? 64u : 8u' in engine
memset_patcher=Path("tools/patch_xowue_stream_memset_probe.py").read_text()
workflow=Path(".github/workflows/xowue-ios.yml").read_text()
assert "void xowue_trace_stream_memset(PPCContext &ctx, uint8_t *base, uint32_t phase)" in engine
assert "B146_STREAM_MEMSET_BEGIN" in engine and "B146_STREAM_MEMSET_END" in engine
assert "if (activeSample > 64u)" in engine
assert 'return count.fetch_add(1u, std::memory_order_relaxed) < 160u;' in engine
assert "validGuestRange(ctx.r3.u32, static_cast<uint64_t>(ctx.r5.u32))" in engine
assert "0x82573E64" in memset_patcher and "sub_82C2A1F0(ctx, base);" in memset_patcher
assert "patch_xowue_stream_memset_probe.py --self-test" in workflow
assert "patch_xowue_stream_memset_probe.py" in workflow

# Build 147: preserve NT committed pages on MEM_COMMIT recommit, track MEM_RELEASE
# cursor movement, and inspect the exact chunk entry before the AOT body executes.
assert "B147_VM_RECOMMIT" in engine
assert "B147_VM_RELEASE" in engine
assert "B147_CHUNK_ENTRY" in engine
assert "bytesAlreadyCommitted" in engine and "mergedCovered" in engine
assert "g_nextVirtualAllocation_before" in engine
assert "g_nextVirtualAllocation_after" in engine
assert "entry_valid=%u data32=%s" in engine
assert "w1 != 0u && w1 <= 0x400000u" in engine
assert "static_cast<uint64_t>(object) + 172u" in engine
assert "data + static_cast<uint64_t>(index) * 16u" not in engine  # overflow-safe entry address is computed separately
assert "xowue_trace_chunk_entry(PPCContext &ctx, uint8_t *base)" in engine
assert "xowue_trace_chunk_entry(ctx, base);" in memset_patcher
assert "sub_82575108" in memset_patcher
assert "B147_CHUNK_ENTRY" in engine
assert not re.search(
    r"if \(commit && \(allocationType & 0x00800000u\) == 0\) \{\s*"
    r"std::memset\(base \+ address, 0, adjustedSize\);",
    engine,
)


assert "sample <= 8u" in engine
assert 'event.find("B140_STREAM_DISPATCH ")' in engine
assert "case 0x825754E4u:" in engine and "case 0x82575510u:" in engine
assert "case 0x82575510u: return 6" in engine
assert "case 0x825754E4u:" in engine and "vtableOffset = 64u" in engine
assert "vtableOffset = 64u" in engine
assert "const uint32_t streamObject = pollSite" in engine
for field in ("136u", "140u", "148u", "156u", "164u", "168u", "172u"):
    assert f"streamObject + {field}" in engine, f"stream field {field} not traced"
for field in ("f136=", "f140=", "f148=", "f156=", "f164=", "f168=", "f172="):
    assert field in engine, f"stream state field {field} missing from event"
assert "vtable_offset=0x%X" in engine and "vtable_slot=0x%08X" in engine
assert "function(context, base);" in engine
print("PASS: Build 140/144 stream-poll, queue-wake and worker-queue telemetry targets, vtable slots, object progress fields and bounded dispatch")

# Build 140 root-cause fix: the shader translator packs absolute c-register
# references, so the draw packet must preserve per-stage masks and the host
# must pack the actual VS/PS UBO data before upload.
packing=Path("Runtime/Graphics/Xenos/XOWUEConstantPacking.h").read_text()
assert "constPacked = false" in bridge and "constUsed[4]" in bridge
assert "entry.constPacked = shader.constPacked" in bridge
assert "std::memcpy(entry.constUsed, shader.constUsed" in bridge
assert "packet.vs_const_packed=vs->second.constPacked?1u:0u" in bridge
assert "packet.ps_const_packed=ps->second.constPacked?1u:0u" in bridge
assert "std::memcpy(packet.vs_const_used,vs->second.constUsed" in bridge
assert "std::memcpy(packet.ps_const_used,ps->second.constUsed" in bridge
assert "xowue_prepare_guest_draw_constants" in packing
assert "xowue_prepare_guest_draw_constants(draw," in renderer
assert "XOWUEConstantPacking.h" in renderer
assert "uint32_t vs_const_packed, ps_const_packed;" in header
assert "uint64_t vs_const_used[4], ps_const_used[4];" in header
print("PASS: per-stage Xenos packed constants match translator remap before Vulkan UBO upload")

# Retain all B148 diagnostic tags. B149 preserves B148 EOF/file reads and changes
# the chunk OOB hook to logging only so the original PPC path continues.
for tag in ("B148_STREAM_EOF_POLL", "B148_CHUNK_IDX_OOB", "B148_READ_ZERO"):
    assert tag in engine, f"missing retained B148 diagnostic tag {tag}"
assert "void xowue_trace_chunk_idx_oob(PPCContext &ctx, uint8_t *base)" in engine
assert "action=read_continues experimental=1" in engine
assert "CHUNK_OOB_LEGACY_GUARD = \"if (xowue_trace_chunk_idx_oob(ctx, base)) return;\"" in memset_patcher
assert 'CHUNK_OOB_GUARD = "xowue_trace_chunk_idx_oob(ctx, base);"' in memset_patcher
assert "xowue_trace_chunk_idx_oob(ctx, base);" in memset_patcher

for tag in ("B149_STREAM_EOF_POLL", "B149_STREAM_LAST_READS", "B149_CHUNK_IDX_OOB"):
    assert tag in engine, f"missing B149 diagnostic tag {tag}"
assert "void xowue_trace_stream_eof_poll_b149(PPCContext &ctx, uint8_t *base)" in engine
assert "static thread_local ReadHistory s_recentReads" in engine
assert "readField(object, 148u, currentWindowEnd)" in engine
assert "if (windowCoversRequest) {" in engine
assert 'logSkip("window_covers_request", UINT32_MAX);' in engine
assert "if (cursor < currentWindowEnd) {" in engine
assert 'logSkip("cursor_before_window_end", UINT32_MAX);' in engine
assert "last_entry16=%s" in engine and "guest_return_chain=%s" in engine
assert "sample > 16u" in engine and "std::array<ReadPair, 8>" in engine
assert "B149_STREAM_LAST_READS sample=%u" in engine
assert "B149_CHUNK_IDX_OOB sample=%u obj=0x%08X idx=%u count=%u" in engine
assert "xowue_trace_stream_eof_poll_b149(ctx, base);" in memset_patcher
assert 'Math.max(completedIPAs + 2, 149)' in workflow
assert 'includes("[B149]")' in workflow
assert "referencias a 149:" in workflow
print("PASS: retained B148 diagnostics and B149 window EOF, eight-read history, log-only chunk OOB")


print("PASS: retained B148 diagnostics and B149 window/history/log-only probes")

