#!/usr/bin/env python3
"""CI: ensure first NV2A Vulkan surface and teardown run on SDL UIKit owner thread."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
native=(root/"port/third_party/xboxrecomp/src/kernel/nv2a_hw_native.inc").read_text()
engine=Path(__file__).resolve().parents[1].joinpath("Native/poptst_engine.c").read_text()
checks={
 "source includes exported iOS claim helper": "extern bool poptst_ios_gpu_claim_window(SDL_GPUDevice *, SDL_Window *);" in native,
 "claim uses main-queue proxy in Apple arm": "#if defined(__APPLE__)\n    if (!s_ng.device || !poptst_ios_gpu_claim_window(s_ng.device, s_ng.window)) goto fail;" in native,
 "release uses main-queue proxy in Apple arm": "#if defined(__APPLE__)\n        if (s_ng.window) poptst_ios_gpu_release_window(s_ng.device, s_ng.window);" in native,
 "only one SDL-host window, not destroyed by NV2A on Apple": "#if !defined(__ANDROID__) && !defined(__APPLE__)\n    if (s_ng.window) SDL_DestroyWindow(s_ng.window);" in native,
 "claim callback is synchronously dispatched on UI main": "dispatch_sync_f(dispatch_get_main_queue(),&op,poptst_gpu_claim_main);" in engine,
 "release callback is synchronously dispatched on UI main": "dispatch_sync_f(dispatch_get_main_queue(),&op,poptst_gpu_release_main);" in engine,
 "main-thread path does not deadlock": "if (pthread_main_np()) poptst_gpu_claim_main(&op);" in engine and "if (pthread_main_np()) poptst_gpu_release_main(&op);" in engine,
 "native GPU initialized milestone": "GPU B23: native NV2A renderer initialized" in native,
 "first real guest frame, only after GPU swapchain": "GPU B23: FIRST REAL NV2A COMPOSED SWAPCHAIN FRAME SUBMITTED" in native and "if (swap)" in native,
 "original Android paths unchanged": "#else\n    if (!s_ng.device || !SDL_ClaimWindowForGPUDevice(s_ng.device, s_ng.window)) goto fail;" in native,
 "B25 GPU submission backpressure": "SDL_WaitForGPUIdle(s_ng.device)" in native and "(submissions % 24ull)==0" in native and "GPU B25: drained GPU queue" in native,
 "B25 GPU submission error diagnostics": "GPU B25 FATAL:" in native and "poptst_engine_trace(detail)" in native and 'ng_fail("submit")' in native,
 "B28 newly allocated composed target initialized before LOAD": "poptst_new_composed" in native and "if (!s_ng.front || poptst_new_composed)" in native,
 "B28 no guest geometry skipped while compiling new PSOs": 'setenv("RESOT_ASYNC_PIPELINES","0",1);' in engine,
 "B24 Metal resource pressure and frame timing": "SDL_SetGPUAllowedFramesInFlight(s_ng.device,1)" in native and "draws_in_command >= 48u && pass" in native and "poptst_ios_fps_presented();" in native,
 "B23.3 window size on main / atomic snapshot GPU": "poptst_ios_gpu_window_size(s_ng.window, &cw, &ch)" in native and "SDL_GetWindowSizeInPixels(window,&w,&h)" in engine and "atomic_load_explicit(&s_gpu_window_width" in engine,
 "B23.3 window flags on main / atomic snapshot GPU": "poptst_ios_gpu_window_flags(s_ng.window)" in native and "SDL_GetWindowFlags(window)" in engine and "atomic_load_explicit(&s_gpu_window_flags" in engine,
 "B23.3 updated each UIKit pump and after SDL_ShowWindow": "poptst_gpu_capture_window_metrics_main();" in engine and engine.count("poptst_gpu_capture_window_metrics_main();") >= 3,
}
for name,passed in checks.items():print(("PASS " if passed else "FAIL ")+name)
if not all(checks.values()):raise SystemExit(1)
