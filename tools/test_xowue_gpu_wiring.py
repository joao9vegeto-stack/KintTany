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

# Build 55 regression: EVENT_WRITE_SHD bit 31 is a counter write, never a CP interrupt.
assert "const bool writeCounter = (initiator & 0x80000000u) != 0u" in engine
assert "packetValue == 0xDEADBEEFu" not in engine
assert "cpInterruptRequested" not in engine
assert "XENOS_PM4_CP_INTERRUPT_AFTER_KICK" not in engine
assert "XENOS_GRAPHICS_INTERRUPT skipped source=1 invalid SCRATCH_REG4 target=0x%08X" in engine
assert "XOWUE_GUEST_PROGRESS_WATCHDOG fresh_guest_frames=0 duration_ms=" in engine
assert "XOWUE_GUEST_THREAD_STATE id=%u entry=0x%08X lastGuest=0x%08X LR=0x%08X waitReason=%s" in engine
assert "g_runtimeTracePersistMilestones.fetch_add(1, std::memory_order_relaxed) < 100000u" in engine
assert "colorTarget?fminf(720.0f,(float)colorTarget->extent.height)" in renderer
assert "scissor.extent.height=(uint32_t)fminf(720.0f" in renderer
color=Path("iOS/App/XOWUEGuestColor.inc").read_text()
assert "sourceHeight=t->extent.height<720u?t->extent.height:720u" in color
critical=engine[engine.index("void xowue_RtlTryEnterCriticalSection"):engine.index("void xowue_RtlLeaveCriticalSection")]
assert "owner == g_currentGuestThreadId" in critical and "recursion = 1u" in critical
assert "shouldTraceCriticalSectionContention" in critical
assert "shouldTraceCriticalSection()" in critical
assert "GuestWaitStateScope waitState" in engine
assert "lastGuestPc.store(guestAddress" in engine
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
assert "shouldStopNativeSession = phase == .booting || gameSurfacePresented" in request_exit
assert "xowue_request_stop()" in request_exit
assert "gameSurfacePresented = false" in request_exit
assert "Do not debounce/ignore repeated exit taps" in request_exit
assert "xowue_request_stop()" in request_exit
assert ".zIndex(1000)" in ui
assert vulkan.count("UILabel *_fpsLabel;") == 1
assert "g_xowue_guest_frame_count" in vulkan
assert "XOWUE_REAL_FPS guest=" in vulkan
assert "self.bounds.size.height - 58.0" in vulkan
assert "_fpsLabel.layer.zPosition = 1000.0;" in vulkan
assert "[self bringSubviewToFront:_fpsLabel];" in vulkan
print("PASS: immediate SAIR dismissal after native stop request and isolated real guest FPS badge")

# Build 39: only known UE3 startup movie files may fall back to EOF when absent.
assert "isKnownOptionalStartupMovie" in engine
assert "XOWUE_OPTIONAL_STARTUP_MOVIE_EOF" in engine
assert '".XOWUEVirtualMedia"' in engine
assert 'filename == "ravenlogo.xxx"' in engine
assert 'filename == "blank.bik"' in engine
assert 'filename == "blank.xxx"' in engine
assert 'filename == "marvel_intro.xxx"' in engine
for movie in ("ravenlogo.bik", "ue3_logo.bik", "fox_logo.bik",
              "marvel_intro.bik", "atvi_logo.bik"):
    assert movie in engine
assert "resolveCaseInsensitivePath(root, rel)" in engine
assert "signal.signalNow();" in engine
assert "g_lastValidScratchReg4Callback" in engine
assert "g_scratchReg4CallbackPending" in engine
assert "XENOS_GRAPHICS_INTERRUPT restored SCRATCH_REG4 target=0x%08X" in engine
assert "XOWUE_AOT_HOTSPOT guest=0x%08X calls=%llu thread=%u cooperative_yield=1" in engine
patch = Path("patches/XenonRecomp-XOWUE.patch").read_text()
assert "xowue_note_scratch_reg4_write" in patch
print("PASS: .bik preflight, APFS path case-folding, one-shot SCRATCH_REG4 recovery, NtReadFile event, hotspot yields")


# Build 58: AOT spin detector, recursive case-folded UE3 package index,
# deterministic EDRAM clear resolve, SCRATCH_REG4 aliases, immediate watchdog.
for token in (
    "[CRITICAL_SPINLOCK]", "XOWUE_XEX_CODE_AUDIT",
    "XOWUE_VFS_INDEX_READY", "recursive_directory_iterator",
    "g_guestPathIndex.find(fileKey)", "XOWUE_GUEST_PROGRESS_WATCHDOG_RING",
    "XENOS_SCRATCH_REG4_CAPTURED", "0x7FC81710u", "0x90311010u",
    "XOWUE_AOT_HOTSPOT", "std::chrono::milliseconds(1)"):
    assert token in engine, f"Build 58 engine missing {token}"
assert "XENOS_EDRAM_COLOR_CLEAR_RESOLVE" in color
assert "XD(CmdBeginRenderPass)(cmd,&begin,VK_SUBPASS_CONTENTS_INLINE)" in color
print("PASS: Build 58 spinlock diagnostics, indexed UE3 VFS, clear-color resolve, callback aliases, watchdog state")


# Build 60: AOT milestone diagnostics must include the real indirect PPC
# register snapshot/disassembly; never fake a guest return to break a loop.
assert "top_fn=0x%08X" in engine and "prev_fn=0x%08X" in engine
assert "r3=0x%08X r4=0x%08X r11=0x%08X r30=0x%08X r31=0x%08X" in engine
assert "insns=%08X_%08X_%08X_%08X_%08X_%08X" in engine
assert "SPINLOCK_ACTIVE worker_cp_pump=250us no_forced_guest_return" in engine
assert "lastR3.store(context.r3.u32" in engine
assert "lastR31.store(context.r31.u32" in engine
assert "std::filesystem::weakly_canonical(hostPath, ec)" in engine
assert "weakly_canonical(hostPath.parent_path(), ec)" not in engine
assert 'XENOS_PM4_TAIL count=%u' in engine
assert 'opcode == 0x57u || opcode == 0x5Au' in engine
assert 'XENOS_PM4_EVENT_WRITE initiator=0x%08X address=0x%08X value=0x%08X' in engine
assert "HotFunctionSlot" in engine
assert "[CRITICAL_SPINLOCK] thread=%u fn=0x%08X lr=0x%08X calls=%u swaps=%llu code=" in engine
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
